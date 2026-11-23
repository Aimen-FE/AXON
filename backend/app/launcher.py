"""Double-click startup for this installation; no login items or global services."""
import argparse
import fcntl
import json
import os
import shutil
import socket
import subprocess
import sys
import time
from contextlib import contextmanager, suppress
from pathlib import Path
from urllib.parse import urlsplit
import httpx
import psutil
from .config import ROOT, Settings
from . import teacher_launch as demo_launch

PRIVATE_URL='http://127.0.0.1:8000'

class LaunchError(RuntimeError):pass


def folder():
    path=ROOT/'data/launcher'
    if path.is_symlink():raise LaunchError('La carpeta del lanzador necesita revisión local')
    path.mkdir(mode=0o700,parents=True,exist_ok=True);path.chmod(0o700)
    return path


@contextmanager
def lock():
    fd=os.open(folder()/'startup.lock',os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'a+b') as stream:
        try:fcntl.flock(stream.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise LaunchError('AXON ya se está iniciando. Espera unos segundos a que se abra la web')
        try:yield
        finally:fcntl.flock(stream.fileno(),fcntl.LOCK_UN)


def get_json(url):
    try:
        with httpx.Client(timeout=3,trust_env=False,follow_redirects=False) as client:
            response=client.get(url)
            if response.status_code!=200:return None
            result=response.json()
            return result if isinstance(result,dict) else None
    except (httpx.HTTPError,ValueError):return None


def busy(host,port):
    try:
        with socket.create_connection((host,port),timeout=1):return True
    except OSError:return False


def spawn(command,env,name):
    path=folder()/(name+'.log');fd=os.open(path,os.O_CREAT|os.O_WRONLY|os.O_APPEND|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'ab') as log:
        return subprocess.Popen(command,cwd=ROOT,env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)


def wait_ready(probe,process,description,seconds=25):
    deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:
        if probe():return
        if process is not None and process.poll() is not None:raise LaunchError(description+' no ha podido arrancar. Revisa los registros del lanzador')
        time.sleep(.25)
    raise LaunchError(description+' no responde todavía. Espera un momento y vuelve a abrir AXON')


def ollama_ready(settings):
    data=get_json(settings.ollama_url+'/api/tags')
    if data is None:return False
    if not isinstance(data.get('models'),list):raise LaunchError('La dirección de Ollama está ocupada por otra aplicación')
    names={m.get('name') for m in data['models'] if isinstance(m,dict) and isinstance(m.get('name'),str)}
    if settings.ollama_model not in names:raise LaunchError('Falta el modelo local '+settings.ollama_model+'. Debe restaurarse antes de iniciar la demostración')
    return True


def existing_ollama_service(settings):
    """Use the installed service's model directory instead of an empty user store."""
    url=urlsplit(settings.ollama_url)
    if url.scheme!='http' or url.hostname not in ('127.0.0.1','localhost','::1') or (url.port or 11434)!=11434:return None
    systemctl=shutil.which('systemctl')
    if not systemctl:return None
    for scope in (['--user'],[]):
        try:
            loaded=subprocess.run([systemctl,*scope,'show','ollama.service','--property=LoadState','--value'],capture_output=True,text=True,timeout=3)
        except (OSError,subprocess.TimeoutExpired):continue
        if loaded.returncode or loaded.stdout.strip()!='loaded':continue
        try:
            started=subprocess.run([systemctl,*scope,'--no-ask-password','start','ollama.service'],capture_output=True,text=True,timeout=25)
        except subprocess.TimeoutExpired:raise LaunchError('El servicio de Ollama tarda en arrancar. Espera un momento y vuelve a abrir AXON')
        if started.returncode:raise LaunchError('El servicio de Ollama necesita autorización del sistema para iniciarse. Activa el servicio Ollama o reinicia el ordenador y vuelve a abrir AXON')
        wait_ready(lambda:ollama_ready(settings),None,'Ollama')
        return {'service':'ollama.service','scope':'user' if scope else 'system'}
    return None


def stop_created(process):
    # Only a child created in this attempt, never a pre-existing server.
    if process.poll() is None:
        process.terminate()
        try:process.wait(timeout=5)
        except subprocess.TimeoutExpired:process.kill();process.wait(timeout=3)


def ensure_ollama(settings):
    if ollama_ready(settings):return None
    url=urlsplit(settings.ollama_url);host=url.hostname;port=url.port or 11434
    if url.scheme!='http' or host not in ('127.0.0.1','localhost','::1'):raise LaunchError('Inicia el servicio local de Ollama que tienes configurado')
    if busy(host,port):raise LaunchError('Ollama no responde y su dirección está ocupada. No se ha detenido ninguna otra aplicación')
    service=existing_ollama_service(settings)
    if service:return service
    binary=shutil.which('ollama') or next((p for p in ('/usr/local/bin/ollama','/usr/bin/ollama') if os.access(p,os.X_OK)),None)
    if not binary:raise LaunchError('No se encuentra Ollama en este ordenador. Debe restaurarse su instalación')
    bind='[::1]' if host=='::1' else '127.0.0.1'
    env=dict(os.environ);env.update(OLLAMA_HOST=f'{bind}:{port}',OLLAMA_NO_CLOUD='1',OLLAMA_NUM_PARALLEL='1',OLLAMA_MAX_LOADED_MODELS='1',OLLAMA_KEEP_ALIVE='2m')
    process=spawn([binary,'serve'],env,'ollama')
    try:
        wait_ready(lambda:ollama_ready(settings),process,'Ollama')
        return demo_launch.process_record(process)
    except Exception:
        stop_created(process);raise


def private_ready():
    data=get_json(PRIVATE_URL+'/api/health')
    return bool(data and data.get('status')=='ok' and data.get('timezone')=='Europe/Madrid' and str(data.get('version','')).startswith('0.'))


def ensure_private():
    if private_ready():return None
    if busy('127.0.0.1',8000):raise LaunchError('La dirección local de AXON está ocupada por otra aplicación. No se ha cerrado ese proceso')
    env=dict(os.environ);env.update(PYTHONPATH=str(ROOT/'backend'),AXON_DATA_DIR=str(ROOT/'data'),AXON_DATABASE_URL=f'sqlite:///{ROOT}/data/axon.sqlite3',AXON_HOST='127.0.0.1',AXON_PORT='8000',AXON_PUBLIC_DEMO='false',AXON_FULL_DEMO='false',AXON_SKIP_DOTENV='false',AXON_REMOTE_DEMO='false',AXON_COOKIE_SECURE='false')
    process=spawn([sys.executable,'-m','app.cli','serve'],env,'axon-privado')
    try:
        wait_ready(private_ready,process,'Tu espacio local de AXON')
        record=demo_launch.process_record(process)
        demo_launch.write(folder()/'private-process.json',record)
        return record
    except Exception:
        stop_created(process);raise


def verify_public(url,seconds=30):
    parts=urlsplit(url or '')
    import re
    if parts.scheme!='https' or parts.username or parts.password or parts.port or not re.fullmatch(r'[a-z0-9-]+\.trycloudflare\.com',parts.netloc):raise LaunchError('Cloudflare no ha devuelto un enlace HTTPS válido')
    deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:
        data=get_json(url+'/api/public/info')
        if data and data.get('public_demo') is True and data.get('full_demo') is True and data.get('demo') is True:return
        time.sleep(.5)
    raise LaunchError('El enlace de Cloudflare aún no responde. Comprueba Internet y vuelve a abrir AXON; no se ha mostrado una página sin verificar')


def stop_all():
    with lock():
        result=demo_launch.stop()
        record=demo_launch.read(folder()/'private-process.json')
        try:
            process=psutil.Process(record['pid'])
            args=process.cmdline()
            if abs(process.create_time()-record['created'])<.05 and Path(process.cwd()).resolve()==ROOT.resolve() and '-m' in args and 'app.cli' in args and 'serve' in args:
                process.terminate()
                try:process.wait(timeout=15)
                except psutil.TimeoutExpired:process.kill();process.wait(timeout=4)
        except (KeyError,psutil.Error,OSError):pass
        result['private_running']=private_ready()
        result['ollama']='El servicio compartido de Ollama se conserva; puede detenerse por separado'
        return result


def start_all(progress=lambda text:None,private_only=False):
    with lock():
        if not (ROOT/'frontend/dist/index.html').is_file():raise LaunchError('Falta la interfaz compilada de AXON. Debe restaurarse la instalación')
        settings=Settings.from_env();progress('Comprobando Ollama…');model=ensure_ollama(settings)
        progress('Preparando tu espacio local…');local=ensure_private()
        if private_only:
            result={'url':PRIVATE_URL,'private_only':True}
        else:
            progress('Iniciando la demostración en Cloudflare…');result=demo_launch.start()
            progress('Comprobando el enlace HTTPS…');verify_public(result.get('url'))
            # Only an actually verified, current public link is offered to the user.
            path=folder()/'enlace-publico.txt'
            fd=os.open(path,os.O_CREAT|os.O_WRONLY|os.O_TRUNC|os.O_NOFOLLOW,0o600)
            with os.fdopen(fd,'w') as stream:stream.write(result['url']+'\n')
        state={'url':result['url'],'private_only':private_only,'started_at':time.time()}
        if model:state['ollama_started']=model
        if local:state['private_started']=local
        demo_launch.write(folder()/'last-start.json',state)
        progress('AXON está lista')
        return result


def desktop_available():return bool(os.getenv('DISPLAY') or os.getenv('WAYLAND_DISPLAY'))


class Progress:
    def __init__(self,enabled):
        self.process=None
        if enabled and desktop_available() and shutil.which('zenity'):
            self.process=subprocess.Popen(['zenity','--progress','--title=Iniciando AXON','--text=Preparando la web…','--pulsate','--auto-close','--no-cancel'],stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,text=True)
    def update(self,text):
        if self.process:
            with suppress(BrokenPipeError,OSError):self.process.stdin.write('# '+text+'\n');self.process.stdin.flush()
    def close(self):
        process=self.process;self.process=None
        if process:
            with suppress(BrokenPipeError,OSError,ValueError):process.stdin.write('100\n');process.stdin.flush();process.stdin.close()
            try:process.wait(timeout=3)
            except subprocess.TimeoutExpired:process.terminate()


def notify(title,text):
    binary=shutil.which('notify-send')
    if binary and desktop_available():subprocess.Popen([binary,'--app-name=AXON','--icon='+str(ROOT/'frontend/public/icon.svg'),title,text],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)


def open_browser(url):
    binary=shutil.which('xdg-open')
    if not binary:raise LaunchError('AXON está en marcha. Abre el enlace guardado en data/launcher/enlace-publico.txt con tu navegador')
    subprocess.Popen([binary,url],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)


def main():
    parser=argparse.ArgumentParser(description='Abrir AXON y su demostración de Cloudflare con doble clic')
    actions=parser.add_mutually_exclusive_group();actions.add_argument('--private',action='store_true',help='Abrir solo la instalación personal local');actions.add_argument('--stop-demo',action='store_true',help='Cerrar solo la demostración pública');actions.add_argument('--stop-all',action='store_true',help='Cerrar la publicación y el AXON privado iniciado por este ejecutable');actions.add_argument('--status',action='store_true',help='Mostrar el estado sin iniciar servicios')
    parser.add_argument('--no-browser',action='store_true');parser.add_argument('--no-window',action='store_true');args=parser.parse_args()
    if args.status:
        print(json.dumps(demo_launch.status(),ensure_ascii=False));return 0
    progress=Progress(not args.no_window)
    try:
        if args.stop_all:
            result=stop_all();title='AXON detenida';message='Se han cerrado AXON y su enlace público. Ollama puede detenerse por separado.'
        elif args.stop_demo:
            result=demo_launch.stop();title='Demostración de AXON detenida';message='El enlace público se ha cerrado. Tu espacio local sigue disponible.'
        else:
            result=start_all(progress.update,args.private);title='AXON está lista';message='Se ha abierto tu espacio local.' if args.private else 'La web está abierta con el enlace actual de Cloudflare.'
        progress.close()
        if not args.stop_demo and not args.stop_all and not args.no_browser:open_browser(result['url'])
        if not args.no_window:notify(title,message)
        print(json.dumps(result,ensure_ascii=False));return 0
    except (LaunchError,ValueError,OSError,RuntimeError,psutil.Error) as exc:
        progress.close();message=str(exc)
        print('AXON: '+message,file=sys.stderr)
        if not args.no_window and desktop_available() and shutil.which('zenity'):
            subprocess.Popen(['zenity','--error','--title=No se pudo abrir AXON','--no-markup','--text='+message],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
        return 1

if __name__=='__main__':raise SystemExit(main())
