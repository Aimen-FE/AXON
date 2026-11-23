import json,os,socket
from dataclasses import replace
from pathlib import Path
import pytest
from sqlalchemy import select
from app.models import Memory,SemanticVector,MemoryRelation,MemoryAnnotation
from app import semantic

def fake_embed(settings,texts):
    return [[1.,0.,0.] if any(w in text.lower() for w in ('tarde','vespertino','noche')) else [0.,1.,0.] for text in texts]

def test_semantic_acl_dates_correction_and_deleted_vectors(app,login,monkeypatch):
    c=login();other=login('alumno2.demo');admin=login('admin.demo')
    monkeypatch.setattr(semantic,'model_path',lambda _:Path('/synthetic/contract-test-model'))
    monkeypatch.setattr(semantic,'embed',fake_embed)
    own=c.post('/api/memory',json={'content':'Prefiero estudiar por la tarde','event_at':'2031-01-10T17:00:00+01:00'}).json()
    c.post('/api/memory',json={'content':'Me concentro mejor por la tarde'})
    other.post('/api/memory',json={'content':'Secreto por la tarde de otra cuenta'})
    assert c.post('/api/semantic/index').json()['indexed']>=2
    result=c.post('/api/semantic/search',json={'query':'horario vespertino','day':'2031-01-10'}).json()
    assert [m['id'] for m in result['memories']]==[own['id']]
    assert other.post('/api/semantic/search',json={'query':'vespertino'}).json()['memories']==[]
    assert admin.post('/api/semantic/search',json={'query':'vespertino'}).json()['memories']==[]
    relations=c.get('/api/semantic/relations').json();assert relations and any(r['kind']=='possible_duplicate' for r in relations)
    assert admin.get('/api/semantic/relations').json()==[]
    assert c.patch('/api/semantic/memories/'+own['id'],json={'state':'confirmed'}).json()['state']=='confirmed'
    assert other.patch('/api/semantic/memories/'+own['id'],json={'state':'confirmed'}).status_code==404
    patch=c.patch('/api/memory/'+own['id'],json={'content':'Prefiero estudiar de madrugada','expected_updated_at':own['updated_at']});assert patch.status_code==200
    with app.state.session_factory() as db:
        assert db.scalar(select(SemanticVector).where(SemanticVector.record_id==own['id'])) is None
        assert db.scalar(select(MemoryAnnotation).where(MemoryAnnotation.memory_id==own['id'])).state=='provisional'
    assert all(own['id'] not in (r['left_id'],r['right_id']) for r in c.get('/api/semantic/relations').json())
    c.post('/api/semantic/index');assert c.delete('/api/memory/'+own['id']).status_code==200
    assert all(m['id']!=own['id'] for m in c.post('/api/semantic/search',json={'query':'madrugada'}).json()['memories'])

def test_semantic_unconfigured_honest_text_fallback(app,login):
    c=login();c.post('/api/memory',json={'content':'Repaso con fichas'})
    r=c.post('/api/semantic/search',json={'query':'fichas'}).json()
    assert not r['semantic']['available'] and r['memories']
    assert c.post('/api/semantic/index').status_code==409

@pytest.mark.skipif(not os.getenv('AXON_SEMANTIC_TEST_DATA'),reason='Modelo real local: prueba de aceptación optativa')
def test_real_multilingual_vectors_without_network(app,login,monkeypatch):
    c=login();app.state.settings=replace(app.state.settings,data_dir=Path(os.environ['AXON_SEMANTIC_TEST_DATA']))
    def no_network(*_args,**_kwargs):raise AssertionError('La inferencia intentó acceder a la red')
    monkeypatch.setattr(socket,'create_connection',no_network)
    a=c.post('/api/memory',json={'content':'Mi bicicleta tiene una rueda pinchada y necesita reparación.'}).json()
    c.post('/api/memory',json={'content':'La receta de tortilla lleva huevos y patatas.'})
    assert c.post('/api/semantic/index').status_code==200
    r=c.post('/api/semantic/search',json={'query':'arreglar el neumático de mi bici'}).json()
    assert r['memories'][0]['id']==a['id'] and r['semantic']['engine']=='fastembed-onnx-local'
