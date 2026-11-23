from conftest import DEMO_TEST_PASSWORD
from dataclasses import replace
from datetime import datetime,timezone
from fastapi.testclient import TestClient
from sqlalchemy import select
from app.main import create_app
from app.models import Conversation,Message,MemorySummary


def send(c,convo,text,key='message-0001'):
    r=c.post(f'/api/conversations/{convo}/messages',json={'content':text,'client_id':key})
    assert r.status_code==200,r.text
    return r.json()


def test_chat_and_memory_persist_after_new_app(app,login):
    c=login();convo=c.post('/api/conversations',json={}).json()['id']
    result=send(c,convo,'Recuerda que mi palabra favorita es azabache')
    assert 'guardado' in result['assistant_message']['content']
    second=create_app(app.state.settings,maintenance=False)
    with TestClient(second) as client:
        r=client.post('/api/auth/login',json={'username':'alumno.demo','password':DEMO_TEST_PASSWORD})
        client.headers['x-csrf-token']=r.json()['csrf_token']
        history=client.get('/api/conversations/'+convo).json()['messages']
        assert len(history)==2
        recall=client.get('/api/memory?q=azabache').json()
        assert len(recall['memories'])==1
        assert 'azabache' in recall['memories'][0]['content']


def test_memory_date_uses_event_date_and_madrid_boundaries(login):
    c=login()
    r=c.post('/api/memory',json={'content':'Acontecimiento de madrugada','event_at':'2026-07-18T22:15:00Z'})
    assert r.status_code==201
    found=c.get('/api/memory?day=2026-07-19').json()
    assert any('madrugada' in m['content'] for m in found['memories'])
    assert not c.get('/api/memory?day=2026-07-18').json()['memories']
    assert c.get('/api/memory?day=2026-02-30').status_code==422


def test_search_handles_accents_and_fts_syntax(login):
    c=login()
    assert c.post('/api/memory',json={'content':'Repasar ecuación, álgebra y moléculas'}).status_code==201
    assert c.get('/api/memory?q=ecuacion').json()['memories']
    assert c.get('/api/memory?q=%22%20OR%20NEAR%20%2A').status_code==200


def test_idempotent_message_retries_do_not_duplicate_operations(login,app):
    c=login();convo=c.post('/api/conversations',json={}).json()['id']
    first=send(c,convo,'Recuerda que estudio con tarjetas')
    second=send(c,convo,'Recuerda que estudio con tarjetas')
    assert first['assistant_message']['id']==second['assistant_message']['id']
    assert len(c.get('/api/conversations/'+convo).json()['messages'])==2
    assert len(c.get('/api/memory?q=tarjetas').json()['memories'])==1


def test_simulated_mode_is_identified_and_no_fake_web_search(login):
    c=login();convo=c.post('/api/conversations',json={}).json()['id']
    r=send(c,convo,'Hola, ¿cómo estás?')
    assert r['assistant_message']['details']['engine']=='simulated'
    assert 'Modo de demostración' in r['assistant_message']['content']
    r=send(c,convo,'Busca en Internet una fórmula','message-0002')
    assert 'no está configurada' in r['assistant_message']['content']


def test_summary_preserves_originals(app,login):
    c=login();convo=c.post('/api/conversations',json={}).json()['id']
    for i in range(7):send(c,convo,'¿Qué asignaturas tengo?',f'summary-{i:04d}')
    with app.state.session_factory() as db:
        summary=db.scalar(select(MemorySummary).where(MemorySummary.conversation_id==convo))
        assert summary and summary.message_count==14
        assert len(list(db.scalars(select(Message).where(Message.conversation_id==convo))))==14


def test_empty_messages_and_private_memory_deletion(login):
    c=login();other=login('alumna.demo')
    convo=c.post('/api/conversations',json={}).json()['id']
    assert c.post(f'/api/conversations/{convo}/messages',json={'content':'  ','client_id':'empty-0001'}).status_code==422
    memory=c.post('/api/memory',json={'content':'Temporal secreto'}).json()
    assert other.delete('/api/memory/'+memory['id']).status_code==404
    assert c.delete('/api/memory/'+memory['id']).status_code==200
    assert not c.get('/api/memory?q=Temporal').json()['memories']
