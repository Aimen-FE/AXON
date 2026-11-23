import csv
import hashlib
import io
import re
import zipfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File, Form, Query
from fastapi.responses import FileResponse,Response
from sqlalchemy import select
from .auth import current_user, get_db
from .models import Document, DocumentChunk, Subject
from .policy import document_filter, get_document, require_group, require_role, audit
from .memory import searched
from .serializers import record

router = APIRouter(prefix='/documents', tags=['Documentos y recuperación'])
ALLOWED = {'.txt','.md','.csv','.pdf','.docx','.xlsx','.pptx','.png','.jpg','.jpeg'}
MAX_TEXT = 500_000


def check_zip(raw, suffix):
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            infos=z.infolist()
            if len(infos)>2000 or sum(i.file_size for i in infos)>40*1024*1024:
                raise HTTPException(413,'Archivo comprimido demasiado grande')
            for i in infos:
                if i.flag_bits & 1 or i.file_size>15*1024*1024 or (i.file_size>1024*1024 and i.file_size/max(1,i.compress_size)>200):
                    raise HTTPException(413,'Archivo comprimido no admitido')
                if '..' in Path(i.filename).parts or i.filename.startswith('/') or 'vbaproject' in i.filename.lower() or '/embeddings/' in i.filename.lower():
                    raise HTTPException(415,'No se admiten macros ni objetos incrustados')
            expected={'.docx':'word/document.xml','.xlsx':'xl/workbook.xml','.pptx':'ppt/presentation.xml'}[suffix]
            if expected not in z.namelist():
                raise HTTPException(415,'El contenido no corresponde al tipo de archivo')
    except zipfile.BadZipFile:
        raise HTTPException(422,'Archivo Office dañado')


def ocr_available():
    from .media import ocr_ready
    return ocr_ready()


def image_text(raw):
    if not ocr_available():raise HTTPException(422,'OCR local no disponible: prepara los modelos de español e inglés')
    from .media import ocr_image
    return ocr_image(raw)


def extract(raw, suffix,max_pdf_pages=100):
    sections=[]
    if suffix in ('.png','.jpg','.jpeg'):
        sections=[('OCR local · revisar posibles errores',image_text(raw))]
    elif suffix in ('.txt','.md','.csv'):
        try:
            value=raw.decode('utf-8-sig')
        except UnicodeDecodeError:
            raise HTTPException(422,'Los archivos de texto deben usar UTF-8')
        if '\x00' in value:
            raise HTTPException(415,'El archivo no es texto válido')
        sections=[('Texto',value[:MAX_TEXT])]
    elif suffix=='.pdf':
        if not raw.startswith(b'%PDF-'):
            raise HTTPException(415,'PDF no válido')
        import subprocess,sys,json
        try:
            out=subprocess.run([sys.executable,'-I','-B',str(Path(__file__).with_name('pdf_worker.py')),str(max_pdf_pages)],input=raw,capture_output=True,timeout=24,cwd='/tmp',env={'LANG':'C.UTF-8','OMP_THREAD_LIMIT':'1'})
            if out.returncode or len(out.stdout)>4*1024**2:raise ValueError()
            parsed=json.loads(out.stdout)
            if parsed.get('error'):raise HTTPException(413 if 'Máximo' in parsed['error'] else 422,parsed['error'])
        except (ValueError,OSError,subprocess.TimeoutExpired):raise HTTPException(422,'No se pudo leer el PDF dentro de los límites locales')
        total=0;scanned=0
        for entry in parsed['sections']:
            i=entry['page']-1;text=entry['text'][:MAX_TEXT-total]
            if entry['scanned']:
                scanned+=1
                if scanned>5:raise HTTPException(413,'Máximo cinco páginas escaneadas por importación; divide el PDF para revisar el OCR')
                import subprocess,tempfile,shutil
                if not shutil.which('pdftoppm'):raise HTTPException(422,'La lectura de PDF escaneado necesita el renderizador local pdftoppm')
                with tempfile.TemporaryDirectory(prefix='axon-pdf-ocr-') as folder:
                    source=Path(folder)/'scan.pdf';source.write_bytes(raw)
                    prefix=Path(folder)/'page'
                    try:
                        subprocess.run([sys.executable,'-I','-B',str(Path(__file__).with_name('pdf_render_worker.py')),'/usr/bin/pdftoppm',str(source),str(prefix),str(i+1)],capture_output=True,timeout=12,check=True,env={'LANG':'C.UTF-8'},cwd=folder)
                    except (OSError,subprocess.SubprocessError):raise HTTPException(422,'No se pudo convertir la página escaneada dentro del límite local')
                    image=prefix.with_suffix('.png')
                    if image.stat().st_size>10*1024**2:raise HTTPException(413,'Página escaneada demasiado grande')
                    text=image_text(image.read_bytes())[:MAX_TEXT-total]
                location=f'Página {i+1} · OCR local, revisar'
            else:location=f'Página {i+1}'
            sections.append((location,text))
            total+=len(text)
            if total>=MAX_TEXT: break
    else:
        check_zip(raw,suffix)
        if suffix=='.docx':
            from docx import Document as WordDocument
            doc=WordDocument(io.BytesIO(raw))
            # python-docx paragraph.text omits tracked insertions. Read current XML text
            # in document order, including w:ins and excluding w:del; never execute fields.
            from docx.oxml.ns import qn
            def current_text(element):
                return ''.join(node.text or '' for node in element.iter(qn('w:t'))
                               if not any(parent.tag==qn('w:del') for parent in node.iterancestors()))
            pieces=[]
            for element in doc.element.body:
                if element.tag==qn('w:p'):
                    pieces.append(current_text(element))
                elif element.tag==qn('w:tbl'):
                    for row in element.findall(qn('w:tr')):
                        pieces.append(' | '.join(current_text(cell) for cell in row.findall(qn('w:tc'))))
            sections=[('Documento', '\n'.join(pieces)[:MAX_TEXT])]
        elif suffix=='.xlsx':
            from openpyxl import load_workbook
            book=load_workbook(io.BytesIO(raw),read_only=True,data_only=True,keep_links=False)
            total=0
            try:
                for sheet in book.worksheets[:20]:
                    values=[]
                    for row in sheet.iter_rows(max_row=min(sheet.max_row or 10000,10000),max_col=50,values_only=True):
                        line=' | '.join(str(x)[:2000] if x is not None else '' for x in row)
                        values.append(line)
                        total+=len(line)
                        if total>=MAX_TEXT: break
                    sections.append((f'Hoja {sheet.title}', '\n'.join(values)))
                    if total>=MAX_TEXT: break
            finally: book.close()
        elif suffix=='.pptx':
            from pptx import Presentation
            deck=Presentation(io.BytesIO(raw))
            total=0
            for i,slide in enumerate(list(deck.slides)[:100]):
                value='\n'.join(s.text for s in slide.shapes if s.has_text_frame)[:MAX_TEXT-total]
                sections.append((f'Diapositiva {i+1}',value))
                total+=len(value)
                if total>=MAX_TEXT: break
    chunks=[]
    for location,value in sections:
        value=re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '',value).strip()
        for start in range(0,len(value),900):
            chunk=value[start:start+1100].strip()
            if chunk:
                chunks.append((f'{location} · fragmento {start//900+1}',chunk))
    if not chunks:
        raise HTTPException(422,'No se encontró texto. OCR para imágenes o PDF escaneados no está configurado')
    return chunks


def retrieve_documents(db,user,query,limit=6,institutional=False,document_ids=None):
    from .relevance import terms,score
    from .models import InstitutionalSource
    words=terms(query)
    if not words:return []
    stmt=select(DocumentChunk,Document).join(Document).where(document_filter(db,user))
    if document_ids is not None:
        stmt=stmt.where(Document.id.in_(document_ids))
    from sqlalchemy.orm import aliased
    from sqlalchemy import exists,or_
    newer=aliased(InstitutionalSource);newdoc=aliased(Document)
    current=select(InstitutionalSource.document_id).join(Document,InstitutionalSource.document_id==Document.id).where(InstitutionalSource.center_id==user.center_id,~exists(select(1).select_from(newer).join(newdoc,newer.document_id==newdoc.id).where(newer.center_id==InstitutionalSource.center_id,newer.source_url==InstitutionalSource.source_url,newdoc.version>Document.version)))
    institutional_ids=select(InstitutionalSource.document_id).where(InstitutionalSource.center_id==user.center_id)
    stmt=stmt.where(or_(Document.id.not_in(institutional_ids),Document.id.in_(current)))
    if institutional:stmt=stmt.where(Document.id.in_(select(InstitutionalSource.document_id).where(InstitutionalSource.center_id==user.center_id)))
    stmt=searched(stmt,db,DocumentChunk,' '.join(words))
    from sqlalchemy import case,literal,text
    title_rank=sum((case((Document.title.ilike('%'+w+'%'),1),else_=0) for w in words),literal(0))
    if db.bind.dialect.name=='sqlite':
        fts=' OR '.join('"'+w+'"' for w in words)
        rank=text("(SELECT bm25(search_index) FROM search_index WHERE search_index MATCH :atlas_terms AND entity='document_chunks' AND record_id=document_chunks.id LIMIT 1)").bindparams(atlas_terms=fts)
        stmt=stmt.order_by(title_rank.desc(),rank,Document.updated_at.desc(),DocumentChunk.ordinal)
    else:stmt=stmt.order_by(title_rank.desc(),Document.updated_at.desc(),DocumentChunk.ordinal)
    rows=list(db.execute(stmt.limit(300)))
    ranked=[(score(query,d.title,c.content),c,d) for c,d in rows]
    ranked=[r for r in ranked if r[0]>0]
    ranked.sort(key=lambda r:r[0],reverse=True)
    selected=[]
    for relevance,c,d in ranked[:limit]:
        meta=db.scalar(select(InstitutionalSource).where(InstitutionalSource.document_id==d.id,InstitutionalSource.center_id==user.center_id))
        item={'document_id':d.id,'title':d.title,'filename':d.filename,'version':d.version,'status':d.status,'source':d.source,'location':c.location,'content':c.content,'chunk_id':c.id,'relevance':round(relevance,2)}
        if meta:item['institutional']={k:getattr(meta,k) for k in ('source_url','published_on','checked_on','academic_year','verification','applicability','authority','category')}
        selected.append(item)
    return selected


@router.get('')
def documents(user=Depends(current_user),db=Depends(get_db)):
    return [record(d,('storage_key',)) for d in db.scalars(select(Document).where(document_filter(db,user)).order_by(Document.updated_at.desc()).limit(300))]


@router.get('/search')
def search(q:str=Query(min_length=1,max_length=300),user=Depends(current_user),db=Depends(get_db)):
    return retrieve_documents(db,user,q)


@dataclass
class PreparedUpload:
    filename: str
    suffix: str
    raw: bytes
    chunks: list[tuple[str, str]]
    checksum: str


def image_signature(raw, suffix):
    signature = bytes.fromhex('89504e470d0a1a0a') if suffix == '.png' else bytes.fromhex('ffd8ff')
    if not raw.startswith(signature):
        raise HTTPException(415, 'El contenido no corresponde al tipo de imagen')


async def prepare_upload(request, file, *, index=True, class_file=False):
    filename=Path((file.filename or 'archivo').replace(chr(92),'/')).name
    if len(filename)>200 or any(ord(c)<32 for c in filename):
        raise HTTPException(422,'Nombre de archivo inválido')
    suffix=Path(filename).suffix.lower()
    if suffix not in ALLOWED:
        raise HTTPException(415,'Formatos disponibles: PDF, TXT, MD, DOCX, XLSX, CSV, PPTX e imágenes PNG/JPEG')
    limit=request.app.state.settings.max_upload
    try:
        raw=await file.read(limit+1)
    finally:
        await file.close()
    if not raw:
        raise HTTPException(422,'El archivo está vacío')
    if len(raw)>limit:
        raise HTTPException(413,'El archivo supera el tamaño permitido')
    chunks = []
    from starlette.concurrency import run_in_threadpool
    if class_file and suffix in ('.png', '.jpg', '.jpeg'):
        image_signature(raw, suffix)
        index = index and ocr_available()
    if index or suffix in ('.txt', '.md', '.csv'):
        try:
            extracted = await run_in_threadpool(extract, raw, suffix)
            chunks = extracted if index else []
        except HTTPException as exc:
            no_text = str(exc.detail).startswith(('No se encontró texto', 'OCR local no disponible'))
            if not class_file or not no_text:
                raise
        except Exception:
            raise HTTPException(422, 'No se pudo extraer el documento. Comprueba su formato')
    elif suffix in ('.docx', '.xlsx', '.pptx'):
        await run_in_threadpool(check_zip, raw, suffix)
    elif suffix == '.pdf' and not raw.startswith(b'%PDF-'):
        raise HTTPException(415, 'PDF no válido')
    return PreparedUpload(filename, suffix, raw, chunks, hashlib.sha256(raw).hexdigest())


@contextmanager
def persist_upload(settings, db, user, upload, **values):
    key = f'{uuid4().hex}{upload.suffix}'
    path = settings.data_dir / 'uploads' / key
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    import os
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(upload.raw)
        obj = Document(
            center_id=user.center_id, owner_id=user.id, filename=upload.filename, storage_key=key,
            checksum=upload.checksum, size=len(upload.raw), **values,
        )
        db.add(obj)
        db.flush()
        db.add_all(DocumentChunk(document_id=obj.id, ordinal=i, content=value, location=location)
                   for i, (location, value) in enumerate(upload.chunks))
        yield obj
    except BaseException:
        path.unlink(missing_ok=True)
        raise


@router.post('',status_code=201)
async def upload(request:Request,file:UploadFile=File(...),title:str=Form(...),access:str=Form('personal'),
                 group_id:str|None=Form(None),subject_id:str|None=Form(None),source:str=Form('Subida manual'),
                 user=Depends(current_user),db=Depends(get_db)):
    if not 1<=len(title.strip())<=180 or not 1<=len(source.strip())<=180:
        raise HTTPException(422,'Título o procedencia inválidos')
    if access not in ('personal','group','center','public'):
        raise HTTPException(422,'Nivel de acceso inválido')
    if access=='group':
        require_group(db,user,group_id,subject_id,write=True)
    elif group_id:
        raise HTTPException(422,'Solo los documentos de grupo llevan grupo')
    if access in ('center','public'):
        require_role(user,'admin')
    if access=='personal' and subject_id:
        subject=db.get(Subject,subject_id)
        if not subject or subject.center_id!=user.center_id:
            raise HTTPException(404,'Asignatura no disponible en el centro')
    prepared=await prepare_upload(request,file)
    if request.app.state.settings.full_demo:
        from .teacher_demo import upload_limit
        upload_limit(db,user,len(prepared.raw))
    from .class_models import ClassFile
    base=select(Document).where(Document.owner_id==user.id,Document.access==access,Document.group_id==group_id,
                                Document.id.not_in(select(ClassFile.document_id)))
    if db.scalar(base.where(Document.checksum==prepared.checksum).limit(1)):
        raise HTTPException(409,'Este documento ya está cargado con el mismo acceso')
    prior=db.scalar(base.where(Document.title==title.strip()).order_by(Document.version.desc()).limit(1))
    from .operations import storage_lock
    with storage_lock(request.app.state.settings):
        with persist_upload(request.app.state.settings,db,user,prepared,group_id=group_id,subject_id=subject_id,
                            title=title.strip(),access=access,source=source.strip(),
                            version=prior.version+1 if prior else 1) as obj:
            if access!='personal':
                audit(db,user,'document_uploaded',obj,{'access':access,'chunks':len(prepared.chunks)})
            db.commit()
    return dict(record(obj,('storage_key',)),chunk_count=len(prepared.chunks))


@router.get('/{document_id}/chunks')
def chunks(document_id:str,user=Depends(current_user),db=Depends(get_db)):
    doc=get_document(db,user,document_id)
    return {'document':record(doc,('storage_key',)),'chunks':[record(c) for c in db.scalars(select(DocumentChunk).where(DocumentChunk.document_id==doc.id).order_by(DocumentChunk.ordinal))]}


@router.get('/{document_id}/download')
def download(document_id:str,request:Request,user=Depends(current_user),db=Depends(get_db)):
    doc=get_document(db,user,document_id)
    return document_download(db, doc, request.app.state.settings)


def document_download(db, doc, settings):
    if doc.storage_key.startswith('generated-') and doc.filename=='axon-material.md':
        text='\n\n'.join(db.scalars(select(DocumentChunk.content).where(DocumentChunk.document_id==doc.id).order_by(DocumentChunk.ordinal)))
        return Response(text,media_type='text/markdown',headers={'Content-Disposition':'attachment; filename="axon-material.md"','Cache-Control':'no-store','X-Content-Type-Options':'nosniff'})
    path=settings.data_dir/'uploads'/doc.storage_key
    if not path.is_file(): raise HTTPException(404,'Archivo no disponible')
    return FileResponse(path,filename=doc.filename,media_type='application/octet-stream',headers={'Cache-Control':'no-store','X-Content-Type-Options':'nosniff'})


@router.delete('/{document_id}')
def delete_document(document_id:str,request:Request,user=Depends(current_user),db=Depends(get_db)):
    doc=get_document(db,user,document_id)
    from .class_models import ClassFile
    if db.scalar(select(ClassFile.id).where(ClassFile.document_id == doc.id)):
        raise HTTPException(409, 'Gestiona este archivo desde Clases')
    if doc.owner_id!=user.id:
        if doc.access=='personal': raise HTTPException(404,'Documento no disponible')
        require_role(user,'admin')
    path=request.app.state.settings.data_dir/'uploads'/doc.storage_key
    from .operations import storage_lock
    with storage_lock(request.app.state.settings):
        audit(db,user,'document_deleted',doc,{'access':doc.access})
        db.delete(doc)
        db.commit()
        path.unlink(missing_ok=True)
    return {'ok':True}
