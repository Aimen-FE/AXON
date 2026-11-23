"""Public demo boundary; fictitious fixtures, no tunnel, email or model network."""
from conftest import DEMO_TEST_PASSWORD
import asyncio,json
from contextlib import ExitStack
from dataclasses import replace
from datetime import timedelta
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select,update,func
from app.config import Settings
from app.main import create_app
from app.models import User,Center,GuestSession,GuestRate,Conversation,Message,Memory,StudySession,Session
from app.db import utcnow
from app import guest

HOST='axon-'+'a'*64+'.localhost'
ORIGIN='https://fixture-guest.trycloudflare.com'

@pytest.fixture
def public(tmp_path):
    local=replace(Settings.from_env(),data_dir=tmp_path,database_url=f'sqlite:///{tmp_path}/public.sqlite3',demo=True,remote_demo=False,public_demo=False,ai_mode='simulated')
    seed=create_app(local,maintenance=False,demo_passwords={})
    with seed.state.session_factory() as db:
        for u in db.scalars(select(User)):u.active=False;u.password_hash=''
        db.commit();(tmp_path/'remote-demo.json').write_text(json.dumps({'profile':'atlas-fictitious-v1','center_id':db.scalar(select(Center.id))}))
    seed.state.engine.dispose()
    (tmp_path/'quick-runtime.json').write_text(json.dumps({'enabled':True,'hostname':'fixture-guest.trycloudflare.com'}))
    settings=replace(local,public_demo=True,cookie_secure=True,session_hours=1,public_origin_host=HOST)
    app=create_app(settings,maintenance=False)
    with ExitStack() as stack:
        def connect(ip='192.0.2.1'):
            client=stack.enter_context(TestClient(app,base_url='https://'+HOST))
            client.headers.update({'Origin':ORIGIN,'CF-Connecting-IP':ip})
            response=client.post('/api/guest/start');assert response.status_code==200,response.text
            client.headers['x-csrf-token']=response.json()['csrf_token'];client.user=response.json()['user']
            return client,response
        yield app,connect
    app.state.engine.dispose()

def test_public_origin_fails_closed_and_has_no_normal_login(public):
    app,connect=public
    with TestClient(app,base_url='https://'+HOST) as c:
        assert c.get('/').status_code==200
        info=c.get('/api/public/info').json();assert info['public_demo'] and info['guest_queries']==20
        assert c.get('/api/auth/me').status_code==401
        for path in ['/api/docs','/api/openapi.json','/api/health','/.env','/data/axon.sqlite3','/api/demo-launch/status','/api/admin/users','/api/remote/readiness']:
            assert c.get(path).status_code==403,path
        assert c.post('/api/auth/login',json={'username':'admin.demo','password':DEMO_TEST_PASSWORD}).status_code==403
        assert c.post('/api/guest/start',headers={'Origin':'https://attacker.example'}).status_code==403
        assert c.post('/api/guest/start').status_code==403
        assert c.get('/api/public/info',headers={'Host':'fixture-guest.trycloudflare.com'}).status_code==403
        runtime=app.state.settings.data_dir/'quick-runtime.json';runtime.write_text(json.dumps({'enabled':False}))
        assert c.get('/').status_code==503

def test_guest_cookie_csrf_separate_conversations_memory_and_tools(public):
    app,connect=public;a,r=connect();b,_=connect('192.0.2.2')
    cookie=r.headers['set-cookie'].lower();assert all(x in cookie for x in ['secure','httponly','samesite=strict','max-age=3600'])
    assert a.user['temporary_guest'] and a.user['role']=='student'
    assert a.user['id']!=b.user['id']
    a.headers.pop('x-csrf-token');assert a.post('/api/conversations',json={}).status_code==403
    a.headers['x-csrf-token']=r.json()['csrf_token']
    convo=a.post('/api/conversations',json={'title':'Solo visitante A'}).json()['id']
    reply=a.post('/api/conversations/'+convo+'/messages',json={'content':'Recuerda que el planeta ficticio se llama AMBAR','client_id':'guest-memory-fixture'})
    assert reply.status_code==200,reply.text
    assert 'sesión temporal' in reply.json()['assistant_message']['content'] and 'otra sesión' not in reply.json()['assistant_message']['content']
    assert a.get('/api/memory?q=AMBAR').json()['memories']
    assert not b.get('/api/memory?q=AMBAR').json()['memories']
    assert b.get('/api/conversations/'+convo).status_code==404
    assert b.post('/api/conversations/'+convo+'/messages',json={'content':'hola','client_id':'intrusion'}).status_code==404
    assert b.post('/api/conversations/'+convo+'/cancel/intrusion').status_code==404
    names={x['name'] for x in a.get('/api/tools').json()};assert names and names<=guest.SAFE_TOOLS
    for name in ['create_event','create_assignment','publish_exam','update_schedule','search_web','fetch_public_url','create_study_plan']:
        assert a.post('/api/tools/call',json={'tool':name,'arguments':{}}).status_code==403,name
    for path in ['/api/admin/center','/api/events','/api/assignments','/api/documents','/api/integrations/classroom/connect','/api/atlas/core/proposals','/api/operations/restore']:
        assert a.post(path,json={}).status_code==403,path
    assert a.get('/api/academic').status_code==200
    assert a.get('/api/schedules').status_code==200
    assert a.get('/api/events').status_code==200
    assert a.get('/api/assignments').status_code==200
    assert a.get('/api/documents').status_code==200

def test_quota_cannot_be_bypassed_by_new_conversation_or_direct_tools(public):
    app,connect=public;c,_=connect()
    with app.state.session_factory() as db:
        db.execute(update(GuestSession).where(GuestSession.user_id==c.user['id']).values(request_count=19));db.commit()
    subject=c.get('/api/academic').json()['subjects'][0]['id']
    study=c.post('/api/study/sessions',json={'subject_id':subject,'topic':'Ecuaciones lineales','mode':'guided'});assert study.status_code==201,study.text
    assert c.get('/api/guest/status').json()['remaining']==0
    convo=c.post('/api/conversations',json={}).json()['id']
    assert c.post('/api/conversations/'+convo+'/messages',json={'content':'hola','client_id':'quota-fixture'}).status_code==429
    assert c.post('/api/tools/call',json={'tool':'query_subjects','arguments':{}}).status_code==429
    assert c.post('/api/math',json={'operation':'simplify','expression':'2+2'}).status_code==429

def test_end_and_expiry_remove_guest_owned_data_without_institutional_changes(public):
    app,connect=public;a,_=connect();b,_=connect('192.0.2.2')
    convo=a.post('/api/conversations',json={}).json()['id']
    a.post('/api/conversations/'+convo+'/messages',json={'content':'Recuerda que prefiero ejemplos ficticios','client_id':'cleanup-fixture'})
    subject=a.get('/api/academic').json()['subjects'][0]['id']
    study=a.post('/api/study/sessions',json={'subject_id':subject,'topic':'Ecuaciones lineales'});assert study.status_code==201
    with app.state.session_factory() as db:
        permanent=set(db.scalars(select(User.id).where(User.preferences['public_guest'].as_boolean().is_not(True))))
    end=a.post('/api/guest/end');assert end.status_code==200,end.text
    with app.state.session_factory() as db:
        assert db.get(User,a.user['id']) is None
        for cls,field in [(GuestSession,GuestSession.user_id),(Session,Session.user_id),(Conversation,Conversation.user_id),(Memory,Memory.user_id),(StudySession,StudySession.user_id)]:assert not db.scalar(select(cls.id).where(field==a.user['id']))
        assert not db.scalar(select(Message.id).where(Message.conversation_id==convo))
        assert permanent<=set(db.scalars(select(User.id)))
        db.execute(update(GuestSession).where(GuestSession.user_id==b.user['id']).values(expires_at=utcnow()-timedelta(seconds=1)));db.commit()
    assert b.get('/api/conversations').status_code==401
    with app.state.session_factory() as db:guest.cleanup(db);assert db.get(User,b.user['id']) is None

def test_start_rate_limit_and_profile_validation(public):
    app,connect=public
    for _ in range(3):connect()
    with TestClient(app,base_url='https://'+HOST,headers={'Origin':ORIGIN,'CF-Connecting-IP':'192.0.2.1'}) as c:
        assert c.post('/api/guest/start').status_code==429
    with app.state.session_factory() as db:
        guest.validate_profile(app.state.settings,db)
        u=db.scalar(select(User).where(User.username=='admin.demo'));u.active=True
        with pytest.raises(ValueError,match='permanente'):guest.validate_profile(app.state.settings,db)
        u.active=False;u.is_demo=False
        with pytest.raises(ValueError,match='personal'):guest.validate_profile(app.state.settings,db)
    with pytest.raises(ValueError,match='independiente'):guest.validate_profile(replace(app.state.settings,cookie_secure=False),None)

def test_shared_ollama_slot_is_released_on_cancel(tmp_path,monkeypatch):
    import app.ai as ai
    monkeypatch.setattr(ai,'ROOT',tmp_path)
    a=ai.OllamaAdapter(Settings.from_env());b=ai.OllamaAdapter(Settings.from_env())
    async def scenario():
        entered=asyncio.Event()
        async def hold():
            async with a.slot(wait=1):entered.set();await asyncio.sleep(20)
        task=asyncio.create_task(hold());await entered.wait()
        with pytest.raises(TimeoutError):
            async with b.slot(wait=.1):pytest.fail('Two processes/adapters acquired the shared inference lock')
        task.cancel()
        with pytest.raises(asyncio.CancelledError):await task
        async with b.slot(wait=1):assert b.active==1
        assert a.active==a.waiting==b.active==b.waiting==0
    asyncio.run(scenario())

def test_cancel_endpoint_is_owner_scoped_and_preserves_message(public):
    from concurrent.futures import ThreadPoolExecutor
    import threading
    app,connect=public;c,_=connect();entered=threading.Event()
    async def generate(*args):
        entered.set();await asyncio.sleep(20)
    app.state.ai.generate=generate
    convo=c.post('/api/conversations',json={}).json()['id']
    with ThreadPoolExecutor() as pool:
        pending=pool.submit(c.post,'/api/conversations/'+convo+'/messages',json={'content':'Explica el ciclo del agua en dos frases','client_id':'cancel-fixture'})
        assert entered.wait(3)
        assert c.post('/api/conversations/'+convo+'/cancel/cancel-fixture').json()['cancelled']
        result=pending.result(timeout=3);assert result.status_code==200,result.text
        assert result.json()['assistant_message']['details']['engine']=='cancelled'
    assert len(c.get('/api/conversations/'+convo).json()['messages'])==2
    assert app.state.chat_inflight==0 and not app.state.active_generations

def test_logout_during_generation_deletes_data_without_dangling_messages(public):
    from concurrent.futures import ThreadPoolExecutor
    import threading
    app,connect=public;c,_=connect();entered=threading.Event()
    async def generate(*args):entered.set();await asyncio.sleep(20)
    app.state.ai.generate=generate
    convo=c.post('/api/conversations',json={}).json()['id']
    with ThreadPoolExecutor() as pool:
        pending=pool.submit(c.post,'/api/conversations/'+convo+'/messages',json={'content':'Explica el ciclo del agua','client_id':'end-fixture'})
        assert entered.wait(3)
        assert c.post('/api/guest/end').status_code==200
        result=pending.result(timeout=3);assert result.status_code==401,result.text
    with app.state.session_factory() as db:
        assert db.get(User,c.user['id']) is None
        assert not db.scalar(select(Message.id).where(Message.conversation_id==convo))
    assert app.state.chat_inflight==0

def test_demo_controls_are_local_admin_only(login):
    student=login();admin=login('admin.demo')
    assert student.get('/api/demo-launch/status').status_code==403
    assert student.post('/api/demo-launch/stop').status_code==403
    result=admin.get('/api/demo-launch/status');assert result.status_code==200,result.text
    assert 'active_guests' in result.json() and 'recent_guests' in result.json()
    assert not any(key in result.json() for key in ['origin','tunnel','pid','origin_host','conversation','cookies'])
    assert admin.post('/api/demo-launch/arbitrary-command').status_code==404

def test_process_control_does_not_adopt_private_process_or_reused_pid(monkeypatch,tmp_path):
    from app import demo_launch
    class Process:
        def create_time(self):return 1234
        def cwd(self):return str(tmp_path)
        def cmdline(self):return ['python','-m','app.cli','serve']
    monkeypatch.setattr(demo_launch,'ROOT',tmp_path)
    monkeypatch.setattr(demo_launch.psutil,'Process',lambda pid:Process())
    assert demo_launch.owned({'pid':123,'created':1234},'origin') is None
    monkeypatch.setattr(Process,'cmdline',lambda self:['python','-m','app.demo_service'])
    assert demo_launch.owned({'pid':123,'created':900},'origin') is None
    assert demo_launch.owned({'pid':123,'created':1234},'origin') is not None
    assert demo_launch.owned({'pid':123,'created':1234},'tunnel') is None
