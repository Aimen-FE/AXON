"""Local OCR and manual voice. No ambient capture or remote audio provider."""
import io,json,os,shutil,subprocess,sys,threading,ctypes.util,wave
from pathlib import Path
from fastapi import APIRouter,Depends,HTTPException,Request,UploadFile,File
from fastapi.responses import Response
from pydantic import BaseModel,Field,ConfigDict
from .config import ROOT
from .auth import current_user
router=APIRouter(prefix='/voice',tags=['Voz local manual'])
_capacity=threading.BoundedSemaphore(1)

def models_root():return Path(os.getenv('AXON_MEDIA_MODELS_DIR',str(ROOT/'data/models'))).resolve()
def ocr_ready():return bool(ctypes.util.find_library('tesseract') and ctypes.util.find_library('seccomp') and all((models_root()/'ocr'/f'{x}.traineddata').is_file() for x in ('spa','eng')))
def status():
    from importlib.util import find_spec
    return {'ocr':ocr_ready(),'transcription':bool(find_spec('vosk') and (models_root()/'vosk-model-small-es-0.42/am/final.mdl').is_file() and ctypes.util.find_library('seccomp')),'speech':bool(shutil.which('espeak-ng')),'processing':'local','manual_recording':True,'audio_retained':False,'max_seconds':60}

def worker(operation,raw):
    if not _capacity.acquire(blocking=False):raise HTTPException(429,'El servicio de lectura local está ocupado. Espera unos segundos')
    try:
        model=models_root()/('ocr' if operation=='ocr' else 'vosk-model-small-es-0.42')
        result=subprocess.run([sys.executable,'-I','-B',str(Path(__file__).with_name('media_worker.py')),operation,str(model)],input=raw,capture_output=True,timeout=28,cwd='/tmp',env={'LANG':'C.UTF-8','OMP_THREAD_LIMIT':'1','OPENBLAS_NUM_THREADS':'1','PYTHONDONTWRITEBYTECODE':'1'})
        if result.returncode or len(result.stdout)>420000:raise HTTPException(422,'No se pudo procesar el archivo dentro de los límites locales. Comprueba su formato y calidad')
        return json.loads(result.stdout)
    except subprocess.TimeoutExpired:raise HTTPException(422,'La lectura local superó el tiempo máximo')
    except (ValueError,OSError):raise HTTPException(503,'El servicio local necesita configuración')
    finally:_capacity.release()

def ocr_image(raw):
    if not ocr_ready():raise HTTPException(422,'OCR local no disponible: faltan los modelos de español e inglés o las bibliotecas locales')
    if not raw or len(raw)>10*1024**2:raise HTTPException(413,'Imagen demasiado grande o vacía')
    return worker('ocr',raw)['text']

@router.get('/status')
def voice_status(user=Depends(current_user)):return status()

@router.post('/transcribe')
async def transcribe(file:UploadFile=File(...),user=Depends(current_user)):
    raw=await file.read(2*1024**2+1);await file.close()
    if len(raw)>2*1024**2:raise HTTPException(413,'Máximo 60 segundos de audio WAV mono a 16 kHz')
    try:
        with wave.open(io.BytesIO(raw),'rb') as audio:
            if audio.getnchannels()!=1 or audio.getsampwidth()!=2 or audio.getframerate()!=16000 or not 0<audio.getnframes()<=960000 or audio.getcomptype()!='NONE':raise ValueError()
            frames=audio.readframes(audio.getnframes())
            if len(frames)!=audio.getnframes()*2:raise ValueError()
    except (wave.Error,ValueError,EOFError):raise HTTPException(415,'Se necesita WAV PCM de 16 bits, mono, 16 kHz y hasta 60 segundos')
    if not status()['transcription']:raise HTTPException(503,'El modelo español de transcripción local no está preparado')
    from starlette.concurrency import run_in_threadpool
    result=await run_in_threadpool(worker,'transcribe',raw)
    return result|{'saved':False,'note':'Revisa el texto antes de enviarlo al chat.'}

class SpeechInput(BaseModel):
    model_config=ConfigDict(extra='forbid')
    text:str=Field(min_length=1,max_length=4000)
    rate:int=Field(default=155,ge=90,le=220)

@router.post('/speech')
def speech(body:SpeechInput,user=Depends(current_user)):
    program=shutil.which('espeak-ng')
    if not program:raise HTTPException(503,'La voz española local no está instalada')
    if not _capacity.acquire(blocking=False):raise HTTPException(429,'El servicio de voz está ocupado')
    try:
        out=subprocess.run([program,'-v','es','-s',str(body.rate),'--stdout','--stdin'],input=body.text.encode(),capture_output=True,timeout=12,env={'LANG':'C.UTF-8'},cwd='/tmp')
        if out.returncode or len(out.stdout)>12*1024**2:raise HTTPException(422,'No se pudo preparar la lectura local')
        raw=bytearray(out.stdout)
        if raw[:4]==b'RIFF' and raw[36:40]==b'data':
            import struct
            struct.pack_into('<I',raw,4,len(raw)-8);struct.pack_into('<I',raw,40,len(raw)-44)
        return Response(bytes(raw),media_type='audio/wav',headers={'Cache-Control':'no-store','X-AXON-Processing':'local'})
    except (OSError,subprocess.TimeoutExpired):raise HTTPException(503,'La voz local no está disponible en este momento')
    finally:_capacity.release()
