import io,subprocess,shutil,wave
from pathlib import Path
import pytest
from app.media import status

def fixture_image():
    from PIL import Image,ImageDraw,ImageFont
    image=Image.new('RGB',(1500,430),'white');font=ImageFont.truetype(str(Path(__file__).resolve().parents[2]/'frontend/public/fonts/AdwaitaSans-Regular.ttf'),40)
    ImageDraw.Draw(image).multiline_text((50,60),'Examen de Matemáticas\nRepasar ecuaciones y funciones',font=font,fill='black',spacing=24)
    return image

@pytest.mark.skipif(not status()['ocr'],reason='Local Spanish OCR model not installed')
def test_real_spanish_image_and_scanned_pdf_ocr(login):
    c=login();im=fixture_image()
    for suffix,fmt in (('png','PNG'),('pdf','PDF')):
        stream=io.BytesIO();im.save(stream,format=fmt)
        result=c.post('/api/documents',data={'title':'Escaneo sintético '+suffix},files={'file':('scan.'+suffix,stream.getvalue(),'application/'+suffix)})
        assert result.status_code==201,result.text
        chunks=c.get('/api/documents/'+result.json()['id']+'/chunks').json();assert 'Matemáticas' in str(chunks) and 'OCR' in str(chunks)

@pytest.mark.skipif(not status()['transcription'] or not status()['speech'] or not shutil.which('ffmpeg'),reason='Local voice assets not installed')
def test_real_local_speech_and_transcription_without_retaining_audio(login,tmp_path):
    c=login();r=c.post('/api/voice/speech',json={'text':'necesito estudiar matematicas','rate':140});assert r.status_code==200
    assert "media-src 'self' blob:" in r.headers['content-security-policy']
    assert r.headers['content-type']=='audio/wav' and r.headers['cache-control']=='no-store'
    path=tmp_path/'voice.wav'
    subprocess.run(['ffmpeg','-v','error','-i','pipe:0','-ar','16000','-ac','1','-f','wav',str(path)],input=r.content,capture_output=True,check=True,timeout=5)
    r=c.post('/api/voice/transcribe',files={'file':('voice.wav',path.read_bytes(),'audio/wav')});assert r.status_code==200,r.text
    assert 'estudiar' in r.json()['text'] and r.json()['saved'] is False
    assert c.post('/api/voice/transcribe',files={'file':('bad.wav',b'invalid','audio/wav')}).status_code==415
