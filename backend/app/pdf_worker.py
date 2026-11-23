"""Bounded PDF text extraction; no network or execution from document content."""
import sys,io,json,resource
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from worker_guard import isolate
resource.setrlimit(resource.RLIMIT_CORE,(0,0));resource.setrlimit(resource.RLIMIT_CPU,(18,20));resource.setrlimit(resource.RLIMIT_AS,(900*1024**2,900*1024**2));resource.setrlimit(resource.RLIMIT_FSIZE,(0,0));resource.setrlimit(resource.RLIMIT_NOFILE,(32,32));resource.setrlimit(resource.RLIMIT_NPROC,(0,0))
from pypdf import PdfReader
isolate()
try:
    raw=sys.stdin.buffer.read(10*1024**2+1)
    if len(raw)>10*1024**2 or not raw.startswith(b'%PDF-'):raise ValueError('PDF no válido')
    reader=PdfReader(io.BytesIO(raw),strict=False)
    if reader.is_encrypted:raise ValueError('No se admiten PDF protegidos por contraseña')
    limit=int(sys.argv[1])
    if limit not in (100,250):raise ValueError('Límite de páginas no válido')
    if len(reader.pages)>limit:raise ValueError(f'Máximo {limit} páginas por PDF')
    sections=[];total=0
    for i,page in enumerate(reader.pages):
        text=(page.extract_text(extraction_mode='layout') or '')[:500000-total]
        scanned=len(text.strip())<30 and bool(page.get('/Resources',{}).get('/XObject',{}))
        sections.append({'page':i+1,'text':text,'scanned':scanned});total+=len(text)
        if total>=500000:break
    print(json.dumps({'sections':sections,'pages':len(reader.pages),'indexed_pages':len(sections),'truncated':len(sections)<len(reader.pages)},ensure_ascii=False))
except ValueError as exc:print(json.dumps({'error':str(exc)[:150]}))
