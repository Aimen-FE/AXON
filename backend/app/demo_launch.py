"""Fixed local launch controls. This module never points a tunnel at the private app."""
import argparse,fcntl,json,os,re,secrets,signal,socket,subprocess,sys,time
from contextlib import contextmanager
from datetime import datetime,timezone
from pathlib import Path
import psutil
from fastapi import APIRouter,Depends,HTTPException,Request
from .config import ROOT
from .auth import current_user
from .policy import require_role
router=APIRouter(prefix='/demo-launch',tags=['Control local de demostración'])

def folder():
    path=ROOT/'data/demo-launch';path.mkdir(parents=True,exist_ok=True,mode=0o700);path.chmod(0o700);return path

def read(path):
    if not path.is_file() or path.is_symlink():return {}
    if path.stat().st_size>10000:raise ValueError('Estado de la demostración fuera de límites')
    return json.loads(path.read_text())

def write(path,data):
    temp=path.with_name(path.name+'.tmp-'+secrets.token_hex(5));fd=os.open(temp,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    with os.fdopen(fd,'w') as out:json.dump(data,out,indent=2)
    os.replace(temp,path)

def runtime_path():return ROOT/'data/atlas-demo/quick-runtime.json'

@contextmanager
def lock():
    with (folder()/'control.lock').open('a+b') as stream:
        os.chmod(stream.name,0o600)
        try:fcntl.flock(stream.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise ValueError('Ya se está cambiando el estado de la demostración')
        try:yield
        finally:fcntl.flock(stream.fileno(),fcntl.LOCK_UN)

def owned(record,kind):
    try:
        p=psutil.Process(record['pid'])
        if abs(p.create_time()-record['created'])>.05 or Path(p.cwd()).resolve()!=ROOT.resolve():return None
        args=p.cmdline()
        if kind=='origin' and not ('-m' in args and 'app.demo_service' in args):return None
        if kind=='tunnel' and Path(args[0]).resolve()!=(ROOT/'data/tools/cloudflared').resolve():return None
        return p
    except (KeyError,psutil.Error,OSError):return None

def process_record(p):return {'pid':p.pid,'created':psutil.Process(p.pid).create_time()}

def status():
    state=read(folder()/'state.json');runtime=read(runtime_path());origin=bool(owned(state.get('origin',{}),'origin'));tunnel=bool(owned(state.get('tunnel',{}),'tunnel'))
    hostname=runtime.get('hostname','');active=origin and tunnel and runtime.get('enabled',False)
    return {'running':bool(active),'origin_running':origin,'tunnel_running':tunnel,'url':'https://'+hostname if active and re.fullmatch(r'[a-z0-9-]+\.trycloudflare\.com',hostname) else None,'temporary_url':True,'guest_minutes':60,'guest_queries':20,'changed_on_restart':True,'started_at':state.get('started_at'),'last_error':state.get('error'),'publication_mode':'public_temporary_guests',**guest_counts()}

def guest_counts():
    path=ROOT/'data/atlas-demo/axon.sqlite3'
    if not path.is_file():return {'active_guests':0,'recent_guests':0}
    import sqlite3
    from datetime import timedelta
    now=datetime.now(timezone.utc)
    try:
        with sqlite3.connect(f'file:{path}?mode=ro',uri=True,timeout=1) as db:
            active,recent=db.execute('SELECT count(*), coalesce(sum(last_seen_at>?),0) FROM guest_sessions WHERE revoked=0 AND expires_at>?',((now-timedelta(minutes=5)).replace(tzinfo=None).isoformat(sep=' '),now.replace(tzinfo=None).isoformat(sep=' '))).fetchone()
        return {'active_guests':active,'recent_guests':recent}
    except sqlite3.Error:return {'active_guests':0,'recent_guests':0}

def stop_internal():
    path=runtime_path();runtime=read(path)
    if path.parent.exists():write(path,{**runtime,'enabled':False})
    state=read(folder()/'state.json');had_origin=owned(state.get('origin',{}),'origin')
    for kind in ('tunnel','origin'):
        p=owned(state.get(kind,{}),kind)
        if p:
            p.terminate()
            try:p.wait(timeout=6)
            except psutil.TimeoutExpired:p.kill();p.wait(timeout=3)
    if had_origin:clear_guests()
    write(folder()/'state.json',{'stopped_at':datetime.now(timezone.utc).isoformat()})
    return status()

def clear_guests():
    # Cleanup remains bounded and confined to the prepared fictitious database,
    # even if graceful origin shutdown had to be cut short.
    from sqlalchemy import select,update,inspect,func
    from .db import create_db
    from .models import Center,User,GuestSession
    from .guest import cleanup
    data=ROOT/'data/atlas-demo';marker=read(data/'remote-demo.json');path=data/'axon.sqlite3'
    if not path.is_file():return
    engine,factory=create_db(f'sqlite:///{path}')
    try:
        if not inspect(engine).has_table('guest_sessions'):return
        with factory() as db:
            if db.scalar(select(Center.id))!=marker.get('center_id') or db.scalar(select(User.id).where(User.is_demo.is_(False))):raise ValueError('No se limpia una base que no esté identificada como ficticia')
            db.execute(update(GuestSession).values(revoked=True));db.commit()
            while db.scalar(select(func.count()).select_from(GuestSession)):
                before=db.scalar(select(func.count()).select_from(GuestSession));cleanup(db)
                if db.scalar(select(func.count()).select_from(GuestSession))>=before:raise ValueError('La limpieza de invitados requiere revisión local')
    finally:engine.dispose()

def stop():
    with lock():return stop_internal()

def start():
    with lock():
        if status()['running']:return status()
        stop_internal()
        data=ROOT/'data/atlas-demo'
        if not (data/'remote-demo.json').is_file():raise ValueError('Prepara la base ficticia independiente antes de publicar')
        binary=ROOT/'data/tools/cloudflared'
        if not binary.is_file() or binary.is_symlink():raise ValueError('Falta el conector verificado del proyecto')
        import hashlib
        manifest=read(ROOT/'data/tools/cloudflared-manifest.json')
        if hashlib.sha256(binary.read_bytes()).hexdigest()!=manifest.get('sha256'):raise ValueError('La huella del conector no coincide con su instalación verificada')
        help_result=subprocess.run([str(binary),'tunnel','--help'],capture_output=True,text=True,timeout=5)
        if help_result.returncode or '--http-host-header' not in help_result.stdout:raise ValueError('El conector no admite el modo previsto')
        with socket.socket() as probe:
            if probe.connect_ex(('127.0.0.1',8015))==0:raise ValueError('El puerto de demostración está ocupado por otro proceso; no se detiene automáticamente')
        origin_host='axon-'+secrets.token_hex(32)+'.localhost';write(runtime_path(),{'enabled':False,'hostname':'','started_at':datetime.now(timezone.utc).isoformat()})
        config=folder()/'cloudflared.yml';config.write_text('{}\n');config.chmod(0o600)
        stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S');origin_log=folder()/('origin-'+stamp+'.log');tunnel_log=folder()/('tunnel-'+stamp+'.log')
        env=dict(os.environ);env.update(PYTHONPATH=str(ROOT/'backend'),AXON_DATA_DIR=str(data),AXON_DATABASE_URL=f'sqlite:///{data}/axon.sqlite3',AXON_PUBLIC_DEMO='true',AXON_PUBLIC_ORIGIN_HOST=origin_host,AXON_REMOTE_DEMO='false',AXON_COOKIE_SECURE='true')
        state={'started_at':datetime.now(timezone.utc).isoformat(),'generation':secrets.token_hex(12)}
        try:
            with origin_log.open('ab') as log:
                origin=subprocess.Popen([sys.executable,'-m','app.demo_service'],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
            origin_log.chmod(0o600);state['origin']=process_record(origin);write(folder()/'state.json',state)
            for _ in range(100):
                if origin.poll() is not None:raise ValueError('La instancia ficticia no arrancó; revisa su registro privado')
                with socket.socket() as probe:
                    if probe.connect_ex(('127.0.0.1',8015))==0:break
                time.sleep(.1)
            else:raise ValueError('La instancia ficticia superó el plazo de arranque')
            args=[str(binary),'tunnel','--no-autoupdate','--config',str(config),'--url','http://127.0.0.1:8015','--http-host-header',origin_host,'--protocol','http2','--metrics','127.0.0.1:0','--loglevel','info']
            # Public guest access was explicitly requested. No email rules or private app origin.
            with tunnel_log.open('ab') as log:
                tunnel=subprocess.Popen(args,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
            tunnel_log.chmod(0o600);state['tunnel']=process_record(tunnel);write(folder()/'state.json',state)
            deadline=time.monotonic()+55;hostname=None
            while time.monotonic()<deadline:
                if tunnel.poll() is not None:raise ValueError('El conector terminó antes de crear el enlace')
                text=tunnel_log.read_text(errors='replace')[-100000:]
                match=re.search(r'https://([a-z0-9-]+\.trycloudflare\.com)',text)
                if match:hostname=match.group(1);break
                time.sleep(.25)
            if not hostname:raise ValueError('Cloudflare no devolvió un enlace dentro del plazo previsto')
            write(runtime_path(),{'enabled':True,'hostname':hostname,'started_at':state['started_at']})
            state['url']='https://'+hostname;write(folder()/'state.json',state)
            return status()
        except Exception as exc:
            stop_internal();write(folder()/'state.json',{'error':str(exc)[:200]});raise

def protect(request,user):
    require_role(user,'admin')
    if request.app.state.settings.public_demo or request.app.state.settings.remote_demo:raise HTTPException(403,'El enlace se gestiona únicamente desde la instalación privada local')
    if not request.client or request.client.host not in ('127.0.0.1','::1','testclient','testserver'):raise HTTPException(403,'Control local requerido')

@router.get('/status')
def api_status(request:Request,user=Depends(current_user)):
    protect(request,user);return status()

@router.post('/{operation}')
def api_control(operation:str,request:Request,user=Depends(current_user)):
    protect(request,user)
    if operation not in ('start','stop','restart'):raise HTTPException(404,'Operación no disponible')
    try:
        if operation=='stop':return stop()
        if operation=='restart':stop()
        return start()
    except (ValueError,OSError) as exc:raise HTTPException(409,str(exc))

def main():
    parser=argparse.ArgumentParser(description='Gestionar la demo pública aislada de AXON, sin modificar la instancia privada')
    parser.add_argument('operation',choices=('start','stop','status','restart','link'));args=parser.parse_args()
    try:
        result=start() if args.operation=='start' else stop() if args.operation=='stop' else (stop(),start())[1] if args.operation=='restart' else status()
        print(result.get('url') or 'La demostración está detenida' if args.operation=='link' else json.dumps(result,ensure_ascii=False))
    except (ValueError,OSError) as exc:parser.exit(1,str(exc)+'\n')
if __name__=='__main__':main()
