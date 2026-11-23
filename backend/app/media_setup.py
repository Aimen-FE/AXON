"""Explicit, reproducible public assets; never downloads on a chat request."""
import hashlib,json,os,shutil,tempfile,time,zipfile,ctypes.util
from pathlib import Path
import httpx
from .config import ROOT

ASSETS=(
 ('ocr/spa.traineddata','https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/main/spa.traineddata','6f2e04d02774a18f01bed44b1111f2cd7f3ba7ac9dc4373cd3f898a40ea6b464',5*1024**2),
 ('ocr/eng.traineddata','https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/main/eng.traineddata','7d4322bd2a7749724879683fc3912cb542f19906c83bcc1a52132556427170b2',6*1024**2),
 ('vosk-small-es.zip','https://alphacephei.com/vosk/models/vosk-model-small-es-0.42.zip','09b239888f633ef2f0b4e09736e3d9936acfd810bc65d53fad45261762c6511f',50*1024**2),
)

def digest(path):
    with path.open('rb') as source:return hashlib.file_digest(source,'sha256').hexdigest()

def download(url,path,expected,limit,client):
    deadline=time.monotonic()+120;size=0
    with client.stream('GET',url) as response:
        response.raise_for_status()
        with path.open('xb') as stream:
            for chunk in response.iter_bytes(65536):
                size+=len(chunk)
                if size>limit or time.monotonic()>deadline:raise ValueError('La descarga superó los límites previstos')
                stream.write(chunk)
    if digest(path)!=expected:raise ValueError('La huella del editor ha cambiado; revisa la nueva versión antes de instalar')
    path.chmod(0o600)

def setup_media():
    root=ROOT/'data/models';root.mkdir(parents=True,exist_ok=True,mode=0o700)
    results=[]
    with tempfile.TemporaryDirectory(prefix='.media-setup-',dir=root) as temporary,httpx.Client(timeout=30,follow_redirects=True,trust_env=False) as client:
        temporary=Path(temporary)
        for name,url,expected,limit in ASSETS:
            target=root/name
            if target.is_symlink():raise ValueError('No se escriben modelos a través de enlaces simbólicos')
            if target.exists():
                if digest(target)!=expected:raise ValueError('El modelo local ha cambiado; no se sobrescribe automáticamente: '+name)
            else:
                temp=temporary/Path(name).name;download(url,temp,expected,limit,client)
                target.parent.mkdir(exist_ok=True,mode=0o700);os.replace(temp,target)
            results.append({'file':name,'url':url,'sha256':expected,'bytes':target.stat().st_size,'license':'Apache-2.0','verification':'SHA-256 fijada de los archivos públicos comprobados el 15-11-2026; no es una firma criptográfica del editor'})
        model=root/'vosk-model-small-es-0.42'
        if not model.exists():
            unpack=temporary/'unpack';unpack.mkdir()
            with zipfile.ZipFile(root/'vosk-small-es.zip') as archive:
                entries=archive.infolist()
                if len(entries)>200 or sum(x.file_size for x in entries)>200*1024**2:raise ValueError('Modelo comprimido fuera de límites')
                for entry in entries:
                    path=Path(entry.filename)
                    if path.is_absolute() or '..' in path.parts or '\\' in entry.filename or path.parts[0]!='vosk-model-small-es-0.42' or ((entry.external_attr>>16)&0o170000)==0o120000:raise ValueError('Ruta no válida dentro del modelo')
                archive.extractall(unpack)
            os.replace(unpack/'vosk-model-small-es-0.42',model)
        if model.is_symlink() or not (model/'am/final.mdl').is_file():raise ValueError('El modelo de dictado no está completo')
    manifest=root/'atlas-models.json';manifest.write_text(json.dumps(results,indent=2));manifest.chmod(0o600)
    from .media import status
    return {'assets':len(results),'status':status(),'dependencies':{'tesseract_library':bool(ctypes.util.find_library('tesseract')),'seccomp_library':bool(ctypes.util.find_library('seccomp')),'pdf_renderer':bool(shutil.which('pdftoppm')),'spanish_speech':bool(shutil.which('espeak-ng'))},'global_packages_installed':False}
