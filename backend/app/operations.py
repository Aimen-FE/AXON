"""Local diagnostics and protected backups. Browser admins never download the private database."""
from collections import deque
from contextlib import contextmanager
from datetime import datetime,timezone,timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
import fcntl,hashlib,json,sqlite3,threading,time,zipfile
from fastapi import APIRouter,Depends,HTTPException,Request
from sqlalchemy import select,func
from alembic.script import ScriptDirectory
from alembic.config import Config
from .auth import current_user,get_db
from .models import ScheduledJob,JobExecution,Center
from .config import ROOT
from .policy import require_role,audit

router=APIRouter(prefix='/admin/operations',tags=['Diagnóstico y respaldo local'])
_backup_lock=threading.Lock()

def file_hash(path):
    with path.open('rb') as source:return hashlib.file_digest(source,'sha256').hexdigest()

@contextmanager
def storage_lock(settings):
    path=settings.data_dir/'.storage.lock'
    with path.open('a+b') as stream:
        path.chmod(0o600);fcntl.flock(stream.fileno(),fcntl.LOCK_EX)
        try:yield
        finally:fcntl.flock(stream.fileno(),fcntl.LOCK_UN)

def folder(settings):
    path=settings.data_dir/'protected-backups';path.mkdir(exist_ok=True,mode=0o700);path.chmod(0o700);return path

def protected_backup(settings,retention_days=14):
    from .backup import backup,restore
    if not settings.database_url.startswith('sqlite'):raise HTTPException(409,'La copia integrada requiere SQLite; usa el procedimiento del operador para PostgreSQL')
    if not _backup_lock.acquire(blocking=False):raise HTTPException(409,'Ya hay una copia de seguridad en curso')
    try:
        target=folder(settings);name='axon-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'.zip'
        with storage_lock(settings):
            from sqlalchemy.engine import make_url
            database=Path(make_url(settings.database_url).database)
            size=database.stat().st_size+sum(p.stat().st_size for p in (settings.data_dir/'uploads').glob('*') if p.is_file() and not p.is_symlink())
            if size>512*1024*1024:raise HTTPException(413,'La copia integrada admite hasta 512 MB. Prepara una copia mediante el operador local')
            archive=backup(settings,target/name)
        # Actual extraction + SQLite/FK validation, followed by hashes for every restored file.
        with TemporaryDirectory(prefix='axon-restore-check-') as temp:
            restored=restore(archive,Path(temp)/'restored')
            with zipfile.ZipFile(archive) as z:
                for info in z.infolist():
                    with z.open(info) as source:expected=hashlib.file_digest(source,'sha256').hexdigest()
                    if expected!=file_hash(restored/info.filename):raise ValueError('La copia no coincide con el contenido restaurado')
            with sqlite3.connect(restored/'axon.sqlite3') as conn:
                tables=conn.execute("SELECT count(*) FROM sqlite_master WHERE type='table'").fetchone()[0]
                migration=conn.execute('SELECT version_num FROM alembic_version').fetchone()[0]
        meta={'name':name,'created_at':datetime.now(timezone.utc).isoformat(),'bytes':archive.stat().st_size,'restored':True,'integrity':'ok','tables':tables,'migration':migration,'sha256':file_hash(archive)}
        manifest=target/(name+'.json');manifest.write_text(json.dumps(meta));manifest.chmod(0o600)
        cutoff=datetime.now(timezone.utc)-timedelta(days=retention_days)
        for entry in target.glob('axon-*.zip.json'):
            try:
                old=json.loads(entry.read_text());old_archive=target/old['name']
                if old_archive.name!=old['name'] or not old_archive.name.startswith('axon-') or not old_archive.name.endswith('.zip'):continue
                if datetime.fromisoformat(old['created_at'])<cutoff and old.get('restored'):
                    old_archive.unlink(missing_ok=True);entry.unlink()
            except (ValueError,OSError,KeyError):continue
        return meta
    finally:_backup_lock.release()

@router.get('/backups')
def backups(request:Request,user=Depends(current_user)):
    require_role(user,'admin');items=[]
    for file in folder(request.app.state.settings).glob('axon-*.zip.json'):
        try:items.append(json.loads(file.read_text()))
        except (ValueError,OSError):continue
    return {'backups':sorted(items,key=lambda x:x['created_at'],reverse=True)[:50],'retention_days':14,
        'download_available':False,'restore':'Restauración por el operador local, con AXON detenido y en una carpeta nueva. Nunca sobrescribe los datos activos.'}

@router.post('/backups',status_code=201)
def create_backup(request:Request,user=Depends(current_user),db=Depends(get_db)):
    require_role(user,'admin');db.commit()
    result=protected_backup(request.app.state.settings)
    from .models import Center
    center=db.get(Center,user.center_id);audit(db,user,'protected_backup_verified',center,{'backup':result['name'],'integrity':result['integrity']});db.commit()
    return result

@router.get('/diagnostics')
async def diagnostics(request:Request,user=Depends(current_user),db=Depends(get_db)):
    require_role(user,'admin')
    import psutil
    from .semantic import semantic_status
    from .documents import ocr_available
    from .classroom import config as classroom_config
    config=Config(str(ROOT/'backend'/'alembic.ini'));head=ScriptDirectory.from_config(config).get_current_head()
    from sqlalchemy import text
    migration=db.execute(text('SELECT version_num FROM alembic_version')).scalar()
    integrity=db.execute(text('PRAGMA quick_check')).scalar() if db.bind.dialect.name=='sqlite' else 'not_applicable'
    faults=len(db.execute(text('PRAGMA foreign_key_check')).fetchall()) if db.bind.dialect.name=='sqlite' else None
    records=list(request.app.state.metrics);latencies=sorted(r['duration_ms'] for r in records)
    memory=psutil.virtual_memory();disk=psutil.disk_usage(str(request.app.state.settings.data_dir))
    ai=await request.app.state.ai.status()
    checks=[{'name':'Base de datos','ok':integrity in ('ok','not_applicable') and faults in (None,0),'recommendation':'Restaura una copia verificada si falla la integridad'},
        {'name':'Migraciones','ok':migration==head,'recommendation':'Detén AXON, crea una copia y ejecuta la actualización compatible'},
        {'name':'Modelo de conversación','ok':ai['available'],'recommendation':'Arranca Ollama y comprueba el modelo configurado; las herramientas locales siguen disponibles'},
        {'name':'Memoria semántica','ok':semantic_status(request.app.state.settings)['available'],'recommendation':'Prepara los archivos locales del modelo; no se descargan durante consultas'}]
    return {'server':'localhost','checked_at':datetime.now(timezone.utc).isoformat(),'cpu_percent':psutil.cpu_percent(interval=None),
        'ram':{'used_percent':memory.percent,'available_bytes':memory.available,'process_bytes':psutil.Process().memory_info().rss},
        'storage':{'free_bytes':disk.free,'used_percent':disk.percent},'ai':ai,'database':{'integrity':integrity,'foreign_key_errors':faults,'migration':migration,'head':head},
        'latency':{'sample_count':len(records),'p50_ms':latencies[len(latencies)//2] if latencies else None,'p95_ms':latencies[min(len(latencies)-1,int(len(latencies)*.95))] if latencies else None},
        'recent_errors':[r for r in records if r['status']>=500][-15:],
        'scheduler':{'enabled_jobs':db.scalar(select(func.count()).select_from(ScheduledJob).where(ScheduledJob.center_id==user.center_id,ScheduledJob.enabled.is_(True),ScheduledJob.cancelled.is_(False)))},
        'integrations':{'classroom_configured':all(classroom_config()),'ocr':ocr_available()},
        'checks':checks,'log_scope':'Últimas 300 peticiones en memoria: ruta de plantilla, estado y duración. Sin mensajes, consultas, nombres, identificadores ni credenciales.',
        'role_blueprints':[{'role':'family','enabled':False,'requires':'Autorización institucional y vínculo explícito con el alumno'},{'role':'direction','enabled':False,'requires':'Permisos institucionales específicos'}]}
