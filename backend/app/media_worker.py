"""One fixed local media operation per short-lived, resource-limited process."""
import os,sys,resource,json,io,ctypes,ctypes.util
resource.setrlimit(resource.RLIMIT_CORE,(0,0))
resource.setrlimit(resource.RLIMIT_CPU,(20,22))
memory=(3*1024**3 if sys.argv[1]=='transcribe' else 1100*1024**2)
resource.setrlimit(resource.RLIMIT_AS,(memory,memory))
resource.setrlimit(resource.RLIMIT_FSIZE,(8*1024**2,8*1024**2))
resource.setrlimit(resource.RLIMIT_NOFILE,(48,48))

from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from worker_guard import isolate as lock_network_and_exec

operation=sys.argv[1];models=sys.argv[2]
if operation=='ocr':
    from PIL import Image,ImageOps
    Image.MAX_IMAGE_PIXELS=20_000_000
    lib=ctypes.CDLL(ctypes.util.find_library('tesseract') or 'libtesseract.so.5')
    lib.TessBaseAPICreate.restype=ctypes.c_void_p
    lib.TessBaseAPIInit3.argtypes=[ctypes.c_void_p,ctypes.c_char_p,ctypes.c_char_p];lib.TessBaseAPIInit3.restype=ctypes.c_int
    lib.TessBaseAPISetImage.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_int]
    lib.TessBaseAPIGetUTF8Text.argtypes=[ctypes.c_void_p];lib.TessBaseAPIGetUTF8Text.restype=ctypes.c_void_p
    lib.TessDeleteText.argtypes=[ctypes.c_void_p];lib.TessBaseAPIDelete.argtypes=[ctypes.c_void_p]
    lib.TessBaseAPISetPageSegMode.argtypes=[ctypes.c_void_p,ctypes.c_int]
    lock_network_and_exec()
    image=Image.open(io.BytesIO(sys.stdin.buffer.read(10*1024**2+1)))
    if image.width*image.height>20_000_000:raise ValueError('Image exceeds limit')
    image=ImageOps.exif_transpose(image).convert('RGB');image.thumbnail((2400,2400))
    handle=lib.TessBaseAPICreate();pointer=None
    try:
        if lib.TessBaseAPIInit3(handle,os.fsencode(models),'spa+eng'.encode())!=0:raise ValueError('OCR languages unavailable')
        data=ctypes.create_string_buffer(image.tobytes())
        lib.TessBaseAPISetImage(handle,data,image.width,image.height,3,image.width*3)
        lib.TessBaseAPISetPageSegMode(handle,3)
        pointer=lib.TessBaseAPIGetUTF8Text(handle)
        text=ctypes.string_at(pointer).decode('utf-8')[:100000] if pointer else ''
    finally:
        if pointer:lib.TessDeleteText(pointer)
        lib.TessBaseAPIDelete(handle)
    print(json.dumps({'text':text,'engine':'tesseract-local-capi','review_required':True}))
elif operation=='transcribe':
    import wave
    from vosk import Model,KaldiRecognizer,SetLogLevel
    SetLogLevel(-1);lock_network_and_exec()
    with wave.open(io.BytesIO(sys.stdin.buffer.read(2*1024**2+1)),'rb') as audio:
        if audio.getnchannels()!=1 or audio.getsampwidth()!=2 or audio.getframerate()!=16000 or audio.getnframes()>16000*60:raise ValueError('Invalid audio')
        model=Model(models);recognizer=KaldiRecognizer(model,16000)
        texts=[]
        while data:=audio.readframes(4000):
            if recognizer.AcceptWaveform(data):texts.append(json.loads(recognizer.Result()).get('text',''))
        texts.append(json.loads(recognizer.FinalResult()).get('text',''))
    print(json.dumps({'text':' '.join(texts).strip()[:6000],'engine':'vosk-local-es','review_required':True}))
else:raise ValueError('Unknown fixed operation')
