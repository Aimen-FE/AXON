"""Detached full-demo lifecycle, with no time cutoff and no system service."""
import argparse,fcntl,hashlib,json,os,re,secrets,socket,subprocess,sys,time
from contextlib import contextmanager
from datetime import datetime,timezone
from pathlib import Path
import httpx,psutil
from fastapi import APIRouter,Depends,HTTPException,Request
from .config import ROOT,Settings
from .auth import current_user
from .policy import require_role
from .demo_launch import read,write,process_record

router=APIRouter(prefix='/demo-launch',tags=['Publicación completa de profesor'])


def origin_port():
    value = os.environ.get('AXON_TEACHER_PORT', '8016')
    if not re.fullmatch(r'[0-9]{4,5}', value) or not 1024 <= int(value) <= 65535:
        raise ValueError('AXON_TEACHER_PORT debe estar entre 1024 y 65535')
    return int(value)

def folder():
    path=ROOT/'data/teacher-launch'
    if path.is_symlink():raise ValueError('Carpeta de control no válida')
    path.mkdir(mode=0o700,parents=True,exist_ok=True);path.chmod(0o700);return path

def data_folder():return ROOT/'data/teacher-demo'
def runtime_path():return data_folder()/'quick-runtime.json'

@contextmanager
def lock():
    fd=os.open(folder()/'control.lock',os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'a+b') as file:
        try:fcntl.flock(file.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise ValueError('Ya se está cambiando el estado de AXON. Espera unos segundos')
        try:yield
        finally:fcntl.flock(file.fileno(),fcntl.LOCK_UN)


def owned(record,kind):
    try:
        p=psutil.Process(record['pid'])
        if abs(p.create_time()-record['created'])>.05 or Path(p.cwd()).resolve()!=ROOT.resolve():return None
        args=p.cmdline()
        if kind=='origin' and not ('-m' in args and 'app.teacher_service' in args):return None
        if kind=='supervisor' and not ('-m' in args and 'app.teacher_launch' in args and 'monitor' in args):return None
        if kind=='tunnel' and Path(args[0]).resolve()!=(ROOT/'data/tools/cloudflared').resolve():return None
        if p.status()==psutil.STATUS_ZOMBIE:return None
        return p
    except (KeyError,psutil.Error,OSError):return None


def counts():
    import sqlite3
    path=data_folder()/'axon.sqlite3'
    if not path.is_file():return {'active_guests':0,'recent_guests':0}
    now=datetime.now(timezone.utc)
    from datetime import timedelta
    try:
        with sqlite3.connect(f'file:{path}?mode=ro',uri=True,timeout=1) as db:
            active,recent=db.execute('SELECT count(*),coalesce(sum(last_seen_at>?),0) FROM teacher_demo_sessions WHERE revoked=0 AND expires_at>?',((now-timedelta(minutes=5)).replace(tzinfo=None).isoformat(sep=' '),now.replace(tzinfo=None).isoformat(sep=' '))).fetchone()
        return {'active_guests':active,'recent_guests':recent}
    except sqlite3.Error:return {'active_guests':0,'recent_guests':0}


def status():
    state=read(folder()/'state.json');control=read(folder()/'control.json');runtime=read(runtime_path())
    origin=bool(owned(state.get('origin',{}),'origin'));tunnel=bool(owned(state.get('tunnel',{}),'tunnel'));supervisor=bool(owned(control.get('supervisor',{}),'supervisor'))
    host=runtime.get('hostname','');valid=bool(re.fullmatch(r'[a-z0-9-]+\.trycloudflare\.com',host));running=origin and tunnel and runtime.get('enabled') and state.get('verified') and valid
    return {'running':bool(running),'origin_running':origin,'tunnel_running':tunnel,'supervisor_running':supervisor,'desired_running':bool(control.get('desired_running')),'url':'https://'+host if running else None,'temporary_url':True,'changed_on_restart':True,'started_at':state.get('started_at'),'last_error':state.get('error'),'publication_mode':'full_teacher_sessions','session_hours':24,'guest_minutes':1440,'guest_queries':100,'query_window':'hour','hard_time_limit_seconds':None,'connection_changes':control.get('connection_changes',0),**counts()}


def terminate(record,kind):
    process=owned(record,kind)
    if not process:return
    process.terminate()
    try:process.wait(timeout=10)
    except psutil.TimeoutExpired:process.kill();process.wait(timeout=4)


def cleanup_sessions():
    path=data_folder()/'axon.sqlite3'
    if not path.is_file():return
    from .db import create_db
    from .teacher_demo import cleanup
    settings=Settings.from_env();from dataclasses import replace
    settings=replace(settings,data_dir=data_folder(),database_url=f'sqlite:///{path}',full_demo=True,public_demo=True)
    engine,factory=create_db(settings.database_url)
    try:
        with factory() as db:cleanup(db,settings,all_sessions=True)
    finally:engine.dispose()


def stop_children():
    runtime=read(runtime_path())
    if data_folder().exists():write(runtime_path(),{**runtime,'enabled':False})
    state=read(folder()/'state.json');had_origin=owned(state.get('origin',{}),'origin')
    terminate(state.get('tunnel',{}),'tunnel');terminate(state.get('origin',{}),'origin')
    if had_origin:cleanup_sessions()
    write(folder()/'state.json',{'stopped_at':datetime.now(timezone.utc).isoformat()})


def public_ready(url):
    try:
        with httpx.Client(timeout=5,trust_env=False,follow_redirects=False) as client:
            response=client.get(url+'/api/public/info')
            return response.status_code==200 and response.json().get('full_demo') is True
    except (httpx.HTTPError,ValueError):return False


def safe_env():
    # The full public process must not read the owner's .env or inherit API keys.
    allowed={'PATH','HOME','USER','LOGNAME','LANG','LANGUAGE','XDG_RUNTIME_DIR','DISPLAY','WAYLAND_DISPLAY','DBUS_SESSION_BUS_ADDRESS','TMPDIR'}
    env={k:v for k,v in os.environ.items() if k in allowed or k.startswith('LC_')}
    env.update(PYTHONPATH=str(ROOT/'backend'),AXON_SKIP_DOTENV='true',AXON_DATA_DIR=str(data_folder()),AXON_DATABASE_URL=f'sqlite:///{data_folder()}/axon.sqlite3',AXON_DEMO='true',AXON_PUBLIC_DEMO='true',AXON_FULL_DEMO='true',AXON_REMOTE_DEMO='false',AXON_COOKIE_SECURE='true',AXON_AI_MODE='ollama',AXON_OLLAMA_MODEL='llama3.2:3b',AXON_MEDIA_MODELS_DIR=str(ROOT/'data/models'))
    settings = Settings.from_env()
    env['AXON_OLLAMA_URL'] = settings.ollama_url
    env['AXON_TEACHER_PORT'] = str(origin_port())
    if settings.pages_origin:
        env['AXON_PAGES_ORIGIN'] = settings.pages_origin
    return env


def spawn(command,env,log):
    fd=os.open(log,os.O_CREAT|os.O_WRONLY|os.O_APPEND|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'ab') as stream:return subprocess.Popen(command,cwd=ROOT,env=env,stdin=subprocess.DEVNULL,stdout=stream,stderr=subprocess.STDOUT,start_new_session=True)


def start_children():
    if status()['running']:return
    stop_children()
    from .teacher_prepare import prepare
    prepare()
    binary=ROOT/'data/tools/cloudflared';manifest=read(ROOT/'data/tools/cloudflared-manifest.json')
    if not binary.is_file() or binary.is_symlink() or hashlib.sha256(binary.read_bytes()).hexdigest()!=manifest.get('sha256'):raise ValueError('El conector no coincide con su instalación verificada')
    env=safe_env()
    port=int(env['AXON_TEACHER_PORT'])
    with socket.socket() as probe:
        if probe.connect_ex(('127.0.0.1',port))==0:raise ValueError('La dirección de profesor está ocupada por otro proceso; no se ha detenido')
    try:
        with httpx.Client(timeout=5,trust_env=False) as client:
            response=client.get(env['AXON_OLLAMA_URL']+'/api/tags');response.raise_for_status()
            if 'llama3.2:3b' not in [m['name'] for m in response.json().get('models',[])]:raise ValueError('Falta el modelo local de la demostración; no se publica un chat simulado')
    except httpx.HTTPError:raise ValueError('Ollama no responde. Abre AXON para iniciar los servicios locales')
    host='axon-'+secrets.token_hex(32)+'.localhost';env['AXON_PUBLIC_ORIGIN_HOST']=host
    write(runtime_path(),{'enabled':False,'hostname':''})
    config=folder()/'cloudflared.yml';config.write_text('{}\n');config.chmod(0o600)
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S');state={'started_at':datetime.now(timezone.utc).isoformat(),'verified':False}
    try:
        process=spawn([sys.executable,'-m','app.teacher_service'],env,folder()/('origin-'+stamp+'.log'));state['origin']=process_record(process);write(folder()/'state.json',state)
        deadline=time.monotonic()+30
        while time.monotonic()<deadline:
            if process.poll() is not None:raise ValueError('La aplicación de profesor no ha arrancado. Revisa su registro local')
            with socket.socket() as probe:
                if probe.connect_ex(('127.0.0.1',port))==0:break
            time.sleep(.15)
        else:raise ValueError('La aplicación de profesor tarda en responder')
        log=folder()/('tunnel-'+stamp+'.log')
        args=[str(binary),'tunnel','--no-autoupdate','--config',str(config),'--url',f'http://127.0.0.1:{port}','--http-host-header',host,'--protocol','http2','--metrics','127.0.0.1:0','--loglevel','info']
        process=spawn(args,{k:v for k,v in env.items() if not k.startswith('AXON_')},log);state['tunnel']=process_record(process);write(folder()/'state.json',state)
        deadline=time.monotonic()+60;hostname=None
        while time.monotonic()<deadline:
            if process.poll() is not None:raise ValueError('Cloudflare terminó antes de devolver la URL')
            match=re.search(r'https://([a-z0-9-]+\.trycloudflare\.com)',log.read_text(errors='replace')[-100000:])
            if match:hostname=match.group(1);break
            time.sleep(.25)
        if not hostname:raise ValueError('Cloudflare no ha devuelto una URL dentro del plazo de arranque')
        write(runtime_path(),{'enabled':True,'hostname':hostname});url='https://'+hostname;deadline=time.monotonic()+360
        while time.monotonic()<deadline:
            if public_ready(url):break
            time.sleep(.5)
        else:raise ValueError('La URL se ha creado, pero todavía no responde por HTTPS; vuelve a iniciar AXON')
        state.update(url=url,verified=True);write(folder()/'state.json',state)
        path=folder()/'enlace-publico.txt';path.write_text(url+'\n');path.chmod(0o600)
        # Disable the former reduced publication only after the full one works.
        from . import demo_launch as legacy
        legacy.stop()
    except Exception as exc:
        stop_children();write(folder()/'state.json',{'error':str(exc)[:240]});raise


def ensure_supervisor():
    control=read(folder()/'control.json')
    if owned(control.get('supervisor',{}),'supervisor'):return
    process=spawn([sys.executable,'-m','app.teacher_launch','monitor'],safe_env(),folder()/'supervisor.log')
    control.update(desired_running=True,supervisor=process_record(process));write(folder()/'control.json',control)


def start():
    with lock():
        start_children();control=read(folder()/'control.json');control['desired_running']=True;write(folder()/'control.json',control);ensure_supervisor();return status()


def stop():
    with lock():
        control=read(folder()/'control.json');control['desired_running']=False;write(folder()/'control.json',control)
        terminate(control.get('supervisor',{}),'supervisor');stop_children();return status()


def monitor():
    # No age/deadline check: the link is not stopped after five or twenty-four hours.
    failures=0;last_probe=0
    while True:
        control=read(folder()/'control.json')
        if not control.get('desired_running'):return
        snapshot=status();healthy=snapshot['running']
        if healthy and time.monotonic()-last_probe>60:
            healthy=public_ready(snapshot['url']);last_probe=time.monotonic()
            failures=0 if healthy else failures+1
        elif not healthy:failures=3
        if failures>=3:
            try:
                with lock():
                    control=read(folder()/'control.json')
                    if not control.get('desired_running'):return
                    previous=snapshot.get('url');stop_children();start_children()
                    control['connection_changes']=control.get('connection_changes',0)+1;write(folder()/'control.json',control);failures=0
                    try:
                        from .launcher import notify
                        notify('El enlace de AXON ha cambiado','Abre AXON para copiar el nuevo enlace de Cloudflare.')
                    except Exception:pass
            except Exception as exc:
                print('Reintento del supervisor: '+type(exc).__name__,flush=True)
                time.sleep(30)
        time.sleep(15)


def protect(request,user):
    require_role(user,'admin')
    if request.app.state.settings.public_demo or request.app.state.settings.remote_demo:raise HTTPException(403,'Control disponible solo en la instalación privada')
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
    parser=argparse.ArgumentParser(description='Publicar AXON completo para profesores en un Quick Tunnel sin corte programado')
    parser.add_argument('operation',choices=('start','stop','restart','status','link','monitor'));args=parser.parse_args()
    if args.operation=='monitor':monitor();return
    try:
        result=start() if args.operation=='start' else stop() if args.operation=='stop' else (stop(),start())[1] if args.operation=='restart' else status()
        print((result.get('url') or 'Publicación detenida') if args.operation=='link' else json.dumps(result,ensure_ascii=False))
    except (ValueError,OSError) as exc:parser.exit(1,str(exc)+'\n')
if __name__=='__main__':main()
