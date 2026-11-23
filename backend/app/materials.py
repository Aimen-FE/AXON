"""Extractive study drafts and reviewed group sharing. Sources retain their ACLs."""
import hashlib
from uuid import uuid4
from fastapi import APIRouter,Depends,HTTPException,Response
from sqlalchemy import select,update
from .auth import current_user,get_db
from .models import MaterialDraft,Document,DocumentChunk,EvaluationCriterion,KnowledgeSource
from .advanced_schemas import MaterialInput,MaterialUpdate
from .knowledge import subject_for
from .documents import retrieve_documents
from .policy import require_group,require_role,get_document,audit
from .serializers import record

router=APIRouter(prefix='/materials',tags=['Materiales revisables'])

def own(db,user,ident):
    obj=db.scalar(select(MaterialDraft).where(MaterialDraft.id==ident,MaterialDraft.user_id==user.id))
    if not obj:raise HTTPException(404,'Material privado no disponible')
    return obj

@router.get('')
def drafts(user=Depends(current_user),db=Depends(get_db)):
    return [record(m) for m in db.scalars(select(MaterialDraft).where(MaterialDraft.user_id==user.id).order_by(MaterialDraft.updated_at.desc()).limit(100))]

@router.post('',status_code=201)
def generate(body:MaterialInput,user=Depends(current_user),db=Depends(get_db)):
    subject=subject_for(db,user,body.subject_id)
    fragments=[f for f in retrieve_documents(db,user,body.query,limit=12) if db.get(Document,f['document_id']).subject_id in (None,subject.id)][:4]
    if not fragments:raise HTTPException(422,'No hay fragmentos autorizados que coincidan. Carga una fuente o ajusta el tema antes de generar el material')
    sources=[{k:f[k] for k in ('document_id','title','location','version','status')} for f in fragments]
    lines=[f'# {body.title}',f'Asignatura: {subject.name}','Borrador de estudio extractivo. Requiere revisión; no es una norma ni calificación oficial.']
    if body.kind in ('summary','outline','exam_guide'):
        lines+=['## Lecturas seleccionadas']
        for i,f in enumerate(fragments,1):lines.extend([f'### {i}. {f["title"]} · {f["location"]}',f['content'][:1700]])
        lines+=['## Repaso propuesto','Explica con tus palabras las ideas anteriores y comprueba cada afirmación en su fuente.']
    elif body.kind in ('quiz','cards'):
        for i,f in enumerate(fragments,1):lines.extend([f'## Actividad {i}',f'Explica la idea principal de «{f["title"]}» y justifícala con un ejemplo propio.',f'Referencia para revisar la respuesta: {f["content"][:700]}'])
    else:
        lines+=['## Rúbrica propuesta','- Precisión conceptual: identificar y definir los conceptos de la fuente.','- Justificación: aportar evidencias y ejemplos.','- Comunicación: presentar un razonamiento claro.','Sin pesos ni nota oficial; el docente debe revisar los descriptores.']
    criteria=list(db.scalars(select(EvaluationCriterion).where(EvaluationCriterion.owner_id==user.id,EvaluationCriterion.subject_id==subject.id).limit(8)))
    if criteria:
        lines+=['## Criterios personales vinculados (revisar)']+[f'{c.code}: {c.content[:300]}' for c in criteria]
        for criterion in criteria:
            origin=db.scalar(select(KnowledgeSource).where(KnowledgeSource.id==criterion.source_id,KnowledgeSource.owner_id==user.id))
            doc=get_document(db,user,origin.document_id) if origin and origin.document_id else None
            if doc and any(s['document_id']==doc.id for s in sources):continue
            sources.append({'document_id':doc.id if doc else None,'title':origin.title if origin else 'Criterio personal sin documento',
                'location':'Criterio '+criterion.code,'version':doc.version if doc else None,'status':doc.status if doc else 'private_statement'})
    lines+=['## Fuentes']+[f'[{i}] {s["title"]} · {s["location"]} · v{s["version"]} · {s["status"]}' for i,s in enumerate(sources,1)]
    obj=MaterialDraft(user_id=user.id,subject_id=subject.id,title=body.title,kind=body.kind,content='\n\n'.join(lines),sources=sources);db.add(obj);db.commit();return record(obj)

@router.patch('/{material_id}')
def edit(material_id:str,body:MaterialUpdate,user=Depends(current_user),db=Depends(get_db)):
    obj=own(db,user,material_id)
    if obj.state=='shared':raise HTTPException(409,'El material ya está compartido. Genera un nuevo borrador para una revisión posterior')
    if body.reviewed:require_role(user,'teacher','admin')
    changed=db.execute(update(MaterialDraft).where(MaterialDraft.id==obj.id,MaterialDraft.user_id==user.id,MaterialDraft.version==body.version).values(content=body.content,version=body.version+1,state='reviewed' if body.reviewed else 'draft')).rowcount
    if not changed:raise HTTPException(409,'El borrador ha cambiado. Actualiza antes de guardar')
    if body.reviewed:audit(db,user,'material_reviewed',obj,{'version':body.version+1})
    db.commit();db.refresh(obj);return record(obj)

@router.get('/{material_id}/export')
def export(material_id:str,user=Depends(current_user),db=Depends(get_db)):
    obj=own(db,user,material_id)
    return Response(obj.content,media_type='text/markdown',headers={'Content-Disposition':'attachment; filename="axon-material.md"','Cache-Control':'no-store'})

def validate_share(db,user,args):
    require_role(user,'teacher','admin');obj=own(db,user,args.material_id)
    require_group(db,user,args.group_id,obj.subject_id,write=True)
    if obj.version!=args.version or obj.state!='reviewed':raise HTTPException(409,'Revisa la versión actual del borrador antes de compartir')
    for source in obj.sources:
        if not source.get('document_id'):raise HTTPException(422,'Un criterio procede de una aportación privada sin documento compartido; revisa las fuentes antes de publicar')
        doc=get_document(db,user,source['document_id'])
        if doc.version!=source['version']:raise HTTPException(409,'Una fuente ha cambiado. Genera y revisa el material actualizado')
        if not (doc.access=='group' and doc.group_id==args.group_id) and not (doc.access in ('center','public') and doc.status in ('validated','official')):
            raise HTTPException(422,'Una fuente es privada o no está disponible para todo el grupo; no puede compartirse mediante este material')
    return obj

def share(db,user,args):
    obj=validate_share(db,user,args)
    # Generated documents have no uploaded executable/binary file; download is rebuilt from the reviewed chunks.
    text=obj.content
    doc=Document(center_id=user.center_id,owner_id=user.id,group_id=args.group_id,subject_id=obj.subject_id,title=obj.title,
        filename='axon-material.md',storage_key='generated-'+uuid4().hex+'.md',checksum=hashlib.sha256(text.encode()).hexdigest(),
        access='group',source='Material revisado y confirmado por docente',status='validated',version=1,size=len(text.encode()))
    db.add(doc);db.flush();db.add(DocumentChunk(document_id=doc.id,ordinal=0,content=text,location='Material revisado · versión '+str(obj.version)))
    obj.state='shared';obj.document_id=doc.id
    from .education import notify_group
    notify_group(db,args.group_id,obj.title,'Material revisado disponible en Documentos','assignment')
    audit(db,user,'material_shared',doc,{'material_id':obj.id,'version':obj.version})
    return {'document_id':doc.id,'material_id':obj.id,'version':obj.version,'shared':True}
