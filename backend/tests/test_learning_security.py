import json,socket,zipfile,io
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
import pytest
from sqlalchemy import select
from fastapi import HTTPException
from app.db import utcnow
from app.models import (User,Subject,KnowledgeSource,PersonalTask,IntegrationConnection,OAuthAttempt,PersonalScheduleSlot,LearnerProfile,Memory,StudySession)
from app import research,classroom
from app.reports import daily_maintenance
from app.auth import digest
from test_learning import learner,policy
from test_memory_chat import send


@pytest.mark.parametrize('url',['http://127.0.0.1','http://169.254.169.254/latest/meta-data/','http://[::1]/','http://10.1.2.3/','http://localhost/','file:///etc/passwd','https://example.org:8080/','http://user:pass@example.org/'])
def test_research_rejects_private_and_unsafe_urls(monkeypatch,url):
    def resolve(host,*args,**kwargs):
        ip=host if ':' in host or host[0].isdigit() else '93.184.216.34'
        return [(socket.AF_INET,socket.SOCK_STREAM,6,'',(ip,80))]
    monkeypatch.setattr(socket,'getaddrinfo',resolve)
    with pytest.raises(HTTPException):research.validate_url(url)


def test_research_blocks_mixed_dns_and_redirect_to_private(monkeypatch):
    monkeypatch.setattr(socket,'getaddrinfo',lambda *a,**k:[(socket.AF_INET,socket.SOCK_STREAM,6,'',('93.184.216.34',80)),(socket.AF_INET,socket.SOCK_STREAM,6,'',('10.0.0.1',80))])
    with pytest.raises(HTTPException):research.validate_url('http://example.org/')


def test_research_does_not_send_private_queries_or_without_consent(app,learner,monkeypatch):
    calls=[]
    monkeypatch.setattr(research,'fetch_public',lambda *a,**k:calls.append(a))
    assert learner.post('/api/research',json={'url':'https://example.org/','consent':False}).status_code==422
    assert learner.post('/api/research',json={'url':'https://example.org/?email=student@example.org','consent':True}).status_code==422
    monkeypatch.setenv('AXON_SEARCH_URL','https://example.org/search')
    assert learner.post('/api/research',json={'query':'mi expediente privado','consent':True}).status_code==422
    assert not calls


def test_research_unconfigured_is_honest_and_public_page_is_not_persisted(app,learner,monkeypatch):
    monkeypatch.delenv('AXON_SEARCH_URL',raising=False)
    result=learner.post('/api/research',json={'query':'tema público','consent':True}).json()
    assert result['available'] is False
    monkeypatch.setattr(research,'fetch_public',lambda *a,**k:{'url':'https://example.org/','mime':'text/html','text':'<title>Fuente de prueba</title><p>Contenido público</p><script>secreto</script>','checked_at':utcnow().isoformat()})
    result=learner.post('/api/research',json={'url':'https://example.org/','consent':True}).json()
    assert 'Contenido público' in result['excerpt'] and 'secreto' not in result['excerpt']
    assert result['persisted'] is False and result['official_school_information'] is False


def test_classroom_requires_configuration_and_explicit_oauth(learner,monkeypatch):
    monkeypatch.delenv('AXON_GOOGLE_CLIENT_ID',raising=False);monkeypatch.delenv('AXON_GOOGLE_CLIENT_SECRET',raising=False)
    assert learner.post('/api/integrations/classroom/authorize').status_code==409
    assert learner.post('/api/integrations/classroom/sync',json={'simulation':False}).status_code==409
    status=learner.get('/api/integrations/classroom').json()
    assert status['configured'] is False and status['connection']['status']=='disconnected'
    simulated=learner.post('/api/integrations/classroom/sync',json={'simulation':True}).json()
    assert simulated['simulation'] and simulated['imported']==0 and learner.get('/api/personal-tasks').json()==[]
    assert learner.post('/api/integrations/classroom/revoke').json()['local_disconnected']


def test_classroom_pkce_state_and_encrypted_storage(app,learner,login,monkeypatch):
    monkeypatch.setenv('AXON_GOOGLE_CLIENT_ID','synthetic-client');monkeypatch.setenv('AXON_GOOGLE_CLIENT_SECRET','synthetic-secret')
    result=learner.post('/api/integrations/classroom/authorize').json()
    from urllib.parse import urlsplit,parse_qs
    args=parse_qs(urlsplit(result['authorization_url']).query);state=args['state'][0]
    assert args['code_challenge_method']==['S256']
    assert all(scope.endswith('.readonly') for scope in args['scope'][0].split())
    assert learner.get('/api/integrations/classroom/callback?state=wrong&code=code').status_code==403
    with app.state.session_factory() as db:
        attempt=db.scalar(select(OAuthAttempt).where(OAuthAttempt.state_hash==digest(state)))
        assert attempt and state not in attempt.encrypted_verifier
        encrypted=classroom.encode(app.state.settings,{'access_token':'test-token-secret'})
        assert 'test-token-secret' not in encrypted
        db.add(IntegrationConnection(user_id=learner.user['id'],provider='classroom',encrypted_payload=encrypted,mode='real',status='connected'));db.commit()
    exported=learner.get('/api/profile/export').text
    assert 'test-token-secret' not in exported and 'encrypted_payload' not in exported and 'encrypted_verifier' not in exported
    assert 'test-token-secret' not in learner.get('/api/integrations/classroom').text
    assert login().get('/api/integrations/classroom').json()['connection']['status']=='disconnected'


def test_personal_notifications_respect_advance_and_deduplicate(app,learner):
    due=(utcnow()+timedelta(hours=30)).isoformat()
    learner.post('/api/personal-tasks',json={'title':'Entrega privada de prueba','due_at':due})
    learner.put('/api/notification-preferences',json={'advance_hours':48,'frequency':'immediate','priority':'all'})
    with app.state.session_factory() as db:daily_maintenance(db);daily_maintenance(db)
    rows=learner.get('/api/notifications').json()
    assert len([n for n in rows if 'Entrega privada' in n['title']])==1
    learner.put('/api/notification-preferences',json={'enabled':False,'advance_hours':48,'frequency':'immediate','priority':'all'})
    learner.post('/api/personal-tasks',json={'title':'Otra entrega silenciada','due_at':due})
    with app.state.session_factory() as db:daily_maintenance(db)
    assert not any('silenciada' in n['title'] for n in learner.get('/api/notifications').json())


def test_plan_confirms_against_changed_availability(learner):
    learner.put('/api/study/availability',json=[{'weekday':i,'starts':'17:00','ends':'19:00'} for i in range(7)])
    plan=learner.post('/api/study/plans',json={'start_day':'2030-12-18','max_sessions':1}).json()
    learner.put('/api/study/availability',json=[])
    assert learner.post('/api/actions/'+plan['action']['id']+'/confirm').status_code==409
    assert learner.get('/api/events').json()==[]


def test_subject_resolution_distinguishes_physics_and_pe(app,learner):
    from app.learning_agent import resolve_subject
    with app.state.session_factory() as db:
        user=db.get(User,learner.user['id']);db.add(Subject(center_id=user.center_id,name='Educación Física'));db.flush()
        assert resolve_subject(db,user,'¿Cuánto valen los exámenes de Física y Química?').name=='Física y Química'
        assert resolve_subject(db,user,'¿Qué profesor de Educación Física tengo?').name=='Educación Física'


def test_formula_question_is_not_an_empty_numeric_calculation(app,learner):
    policy(app,learner,'philosophy')
    convo=learner.post('/api/conversations',json={}).json()['id']
    answer=send(learner,convo,'¿Cómo se calcula la nota final de Filosofía?')['assistant_message']
    assert '0,20' in answer['content'] and answer['details']['tools'][0]['name']=='query_knowledge'


def test_philosophy_target_uses_final_weights_and_reports_limits(app,learner):
    ident,_=policy(app,learner,'philosophy')
    result=learner.post('/api/knowledge/calculate',json={'policy_id':ident,'operation':'target','unknown_component':'e3','target':5,'values':{'e1':5,'e2':5}}).json()
    assert result['required']=='5' and not result['official'] and result['warnings']


def test_private_academic_data_export_and_erase(app,learner):
    ident,_=policy(app,learner)
    data=learner.get('/api/profile/export').json()
    assert data['academic_knowledge']['policies'][0]['id']==ident and data['learner_profile']
    result=learner.request('DELETE','/api/profile/data',json={'password':'Synthetic-Password!2026','confirmation':'ELIMINAR MIS DATOS'})
    assert result.status_code==200,result.text
    with app.state.session_factory() as db:
        assert not db.scalar(select(LearnerProfile).where(LearnerProfile.user_id==learner.user['id']))
        assert not db.scalar(select(KnowledgeSource).where(KnowledgeSource.owner_id==learner.user['id']))
        assert not db.get(User,learner.user['id']).active


def test_optional_ocr_fails_clearly_when_not_installed(learner,monkeypatch):
    from app import documents
    monkeypatch.setattr(documents,'ocr_available',lambda:False)
    result=learner.post('/api/documents',data={'title':'Escaneo de prueba'},files={'file':('scan.png',b'not an image','image/png')})
    assert result.status_code==422 and 'OCR local no disponible' in result.text


def test_backup_restores_integration_key_with_encrypted_tokens(app,learner,tmp_path):
    from dataclasses import replace
    from app.backup import backup,restore
    settings=app.state.settings
    encrypted=classroom.encode(settings,{'refresh_token':'synthetic-refresh-token'})
    output=backup(settings,tmp_path/'academic-backup.zip')
    restored=restore(output,tmp_path/'restored-academic')
    other=replace(settings,data_dir=restored)
    assert classroom.decode(other,encrypted)['refresh_token']=='synthetic-refresh-token'
    assert (restored/'secrets/integrations.key').stat().st_mode&0o777==0o600


def test_manual_source_preserves_provenance_and_checks_weights(learner,login):
    subject=learner.get('/api/academic').json()['subjects'][0]['id']
    body={'subject_id':subject,'title':'Información transcrita de prueba','text':'Información facilitada por el estudiante de prueba. Validación institucional pendiente.','academic_year':'2025-2026','final_weights':[20,40,40]}
    result=learner.post('/api/knowledge/manual',json=body)
    assert result.status_code==201,result.text
    assert result.json()['source']['verification']=='historical'
    assert login().get('/api/knowledge').json()['sources']==[]
    body['final_weights']=[20,40,50]
    assert learner.post('/api/knowledge/manual',json=body).status_code==422


def test_configured_retention_preserves_explicit_memories(app,learner):
    from app.models import Conversation,Message
    old=utcnow()-timedelta(days=100)
    with app.state.session_factory() as db:
        user=db.get(User,learner.user['id']);user.preferences={**user.preferences,'conversation_retention_days':90}
        convo=Conversation(user_id=user.id,title='Conversación caducada',created_at=old,updated_at=old);db.add(convo);db.flush();cid=convo.id
        db.add(Message(conversation_id=cid,role='user',content='Texto antiguo'))
        db.add(Memory(user_id=user.id,content='Recuerdo explícito que se conserva'))
        db.commit();daily_maintenance(db)
        assert db.get(Conversation,cid) is None
        assert db.scalar(select(Memory).where(Memory.user_id==user.id))


def test_relative_weekday_does_not_confuse_morning_with_tomorrow(monkeypatch):
    from app import agent
    from datetime import datetime,timezone
    monkeypatch.setattr(agent,'utcnow',lambda:datetime(2026,11,16,12,tzinfo=timezone.utc))
    assert agent.parse_day('el jueves a las cinco de la mañana').isoformat()=='2026-11-19'
    assert agent.parse_day('el viernes de la semana que viene').isoformat()=='2026-11-27'


def test_research_revalidates_redirect_before_connecting(monkeypatch):
    connections=[]
    def dns(host,*args,**kwargs):return [(socket.AF_INET,socket.SOCK_STREAM,6,'',(host if host=='127.0.0.1' else '93.184.216.34',80))]
    class Redirect:
        status=302
        def getheader(self,key,default=None):return 'http://127.0.0.1/private' if key=='Location' else default
    class Connection:
        def __init__(self,host,port,ip):connections.append(host)
        def request(self,*args,**kwargs):pass
        def getresponse(self):return Redirect()
        def close(self):pass
    monkeypatch.setattr(socket,'getaddrinfo',dns);monkeypatch.setattr(research,'PinnedHTTP',Connection)
    with pytest.raises(HTTPException) as error:research.fetch_public('http://example.org/')
    assert error.value.status_code==403 and connections==['example.org']


def test_classroom_contract_preserves_utc_and_missing_due_time(app,learner,monkeypatch):
    # Mock API contract, not a live Google account authorization.
    class Response:
        def __init__(self,payload):self.payload=payload
        def raise_for_status(self):pass
        def json(self):return self.payload
    class Client:
        def __init__(self,*args,**kwargs):pass
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def get(self,url,**kwargs):
            if url.endswith('/courses'):return Response({'courses':[{'id':'course','name':'Curso ficticio'}]})
            if url.endswith('/courseWorkMaterials'):return Response({'courseWorkMaterial':[{'title':'Material ficticio','description':'Descripción autorizada'}]})
            return Response({'courseWork':[{'id':'task1','title':'Entrega con hora','dueDate':{'year':2030,'month':12,'day':19},'dueTime':{'hours':9}},{'id':'task2','title':'Entrega sin hora','dueDate':{'year':2030,'month':12,'day':20}}]})
    with app.state.session_factory() as db:
        db.add(IntegrationConnection(user_id=learner.user['id'],provider='classroom',mode='real',status='connected',encrypted_payload=classroom.encode(app.state.settings,{'access_token':'synthetic-token'}),expires_at=utcnow()+timedelta(hours=1)));db.commit()
    monkeypatch.setattr(classroom.httpx,'Client',Client)
    result=learner.post('/api/integrations/classroom/sync',json={'simulation':False})
    assert result.status_code==200,result.text
    assert result.json()['imported']==1 and len(result.json()['pending_dates'])==1 and result.json()['materials_read']==1
    tasks=learner.get('/api/personal-tasks').json()
    assert len(tasks)==1 and tasks[0]['due_at']=='2030-12-19T09:00:00+00:00'


def test_event_links_recheck_owner_and_dashboard_includes_personal_tasks(learner,login):
    convo=learner.post('/api/conversations',json={}).json()['id']
    answer=send(learner,convo,'Añade una sesión de estudio el 19 de diciembre de 2030 a las 17:00')['assistant_message']
    assert answer['details']['event_ids'] and not answer['details']['actions']
    ident=answer['details']['event_ids'][0]
    assert learner.get('/api/events/'+ident).status_code==200
    assert login().get('/api/events/'+ident).status_code==404
    task=learner.post('/api/personal-tasks',json={'title':'Tarea propia en el panel','due_at':'2030-12-19T19:00:00+01:00'}).json()
    assert task['id'] in [t['id'] for t in learner.get('/api/dashboard').json()['personal_tasks']]


def test_study_logarithms_are_not_selected_for_technology_or_logic():
    from app.study import exercise
    assert exercise('Tecnología sostenible','Tecnología e Ingeniería',1,0)['kind']=='reflection'
    assert exercise('Lógica y argumentación','Filosofía',1,0)['kind']=='reflection'
    assert exercise('Logaritmos','Matemáticas I',1,0)['kind']=='numeric'
