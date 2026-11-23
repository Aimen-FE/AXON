"""Explicit operator action; never invoked by a chat, inference or scheduled job."""
import json,os
from pathlib import Path

def setup_semantic(settings):
    cache=settings.data_dir/'models';cache.mkdir(parents=True,exist_ok=True,mode=0o700)
    os.environ['ORT_DISABLE_TELEMETRY']='1'
    os.environ['HF_HOME']=str(cache/'hf')
    os.environ['HF_HUB_DISABLE_IMPLICIT_TOKEN']='1'
    os.environ['HF_HUB_DISABLE_TELEMETRY']='1'
    os.environ['XDG_CACHE_HOME']=str(cache/'cache')
    import onnxruntime
    onnxruntime.disable_telemetry_events()
    from fastembed import TextEmbedding
    from .semantic import MODEL
    model=TextEmbedding(MODEL,cache_dir=str(cache),threads=2,providers=['CPUExecutionProvider'])
    path=Path(model.model._model_dir).resolve()
    if not path.is_relative_to(cache.resolve()):raise ValueError('El modelo no se ha preparado dentro de AXON')
    vector=next(model.embed(['Prueba pública de memoria local.']))
    if len(vector)!=384:raise ValueError('El modelo devolvió dimensiones incompatibles')
    manifest=cache/'semantic-model.json'
    manifest.write_text(json.dumps({'model':MODEL,'path':str(path.relative_to(cache.resolve())),'dimensions':384,'license':'Apache-2.0'}));manifest.chmod(0o600)
    return {'model':MODEL,'dimensions':384,'ready':True,'directory':str(cache)}
