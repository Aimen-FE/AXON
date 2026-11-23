"""Full teacher sessions have real role checks and independent fictitious schools."""
import json
from dataclasses import replace
from contextlib import ExitStack
from datetime import timedelta
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select,func,update
from app.main import create_app
from app.config import Settings
from app.models import User,Center,TeacherDemoSession,Document,Message,Conversation,CalendarEvent,Teaching
from app import teacher_demo
from app.db import utcnow

HOST='axon-'+'b'*64+'.localhost'
ORIGIN='https://teacher-fixture.trycloudflare.com'

@pytest.fixture
def full(tmp_path):
    local=replace(Settings.from_env(),data_dir=tmp_path,database_url=f'sqlite:///{tmp_path}/teacher.sqlite3',demo=True,public_demo=False,full_demo=False,remote_demo=False,ai_mode='simulated')
    seed=create_app(local,maintenance=False,demo_passwords={})
    with seed.state.session_factory() as db:
        for u in db.scalars(select(User)):u.active=False;u.password_hash=''
        base=db.scalar(select(Center.id));db.commit()
    seed.state.engine.dispose()
    (tmp_path/'remote-demo.json').write_text(json.dumps({'profile':'teacher-fictitious-v1','center_id':base,'personal_data_copied':False}))
    (tmp_path/'quick-runtime.json').write_text(json.dumps({'enabled':True,'hostname':'teacher-fixture.trycloudflare.com'}))
    settings=replace(local,full_demo=True,public_demo=True,cookie_secure=True,public_origin_host=HOST)
    app=create_app(settings,maintenance=False)
    with ExitStack() as stack:
        def connect():
            c=stack.enter_context(TestClient(app,base_url='https://'+HOST,headers={'Origin':ORIGIN,'CF-Connecting-IP':'198.51.100.9'}))
            r=c.post('/api/teacher-demo/start');assert r.status_code==200,r.text
            c.headers['x-csrf-token']=r.json()['csrf_token'];c.user=r.json()['user'];return c,r
        yield app,connect,base
    app.state.engine.dispose()


def test_full_teacher_role_and_same_wifi_isolation(full):
    app,connect,base=full;clients=[connect()[0] for _ in range(5)]
    assert len({c.user['id'] for c in clients})==5
    assert len({c.user['center_id'] for c in clients})==5
    a,b=clients[:2]
    assert a.user['role']=='teacher' and a.user['demo_teacher'] and not a.user['temporary_guest']
    for c in clients:
        assert c.get('/api/academic').status_code==200
        assert c.get('/api/ai/providers').status_code==200
        assert c.get('/api/semantic/status').status_code in (200,404)
        assert c.get('/api/integrations/classroom').status_code==200
        assert c.get('/api/teacher-demo/status').json()['isolated_school']
    convo=a.post('/api/conversations',json={}).json()['id']
    reply=a.post('/api/conversations/'+convo+'/messages',json={'client_id':'teacher-isolation','content':'Recuerda que mi ejemplo se llama PRUEBA_PROFESOR.'})
    assert reply.status_code==200,reply.text
    assert a.get('/api/memory?q=PRUEBA_PROFESOR').json()['memories']
    assert not b.get('/api/memory?q=PRUEBA_PROFESOR').json()['memories']
    assert b.get('/api/conversations/'+convo).status_code==404
    assert b.get('/api/groups/'+a.user['group_ids'][0]+'/students').status_code in (403,404)


def test_teacher_can_confirm_fictitious_exam_but_not_others_school(full):
    app,connect,base=full;a,_=connect();b,_=connect()
    meta=a.get('/api/academic').json();teaching=next(t for t in meta['teaching'] if t['teacher_id']==a.user['id'])
    body={'title':'Examen ficticio autorizado','kind':'exam','visibility':'group','group_id':teaching['group_id'],'subject_id':teaching['subject_id'],'starts_at':'2030-12-19T09:00:00+01:00','ends_at':'2030-12-19T10:00:00+01:00','syllabus':'Ejemplo inventado'}
    proposed=a.post('/api/tools/call',json={'tool':'publish_exam','arguments':body});assert proposed.status_code==200,proposed.text
    action=proposed.json()['action'];assert not any(e['title']==body['title'] for e in a.get('/api/events').json())
    confirmed=a.post('/api/actions/'+action['id']+'/confirm',json={});assert confirmed.status_code==200,confirmed.text
    assert any(e['title']==body['title'] for e in a.get('/api/events').json())
    assert not any(e['title']==body['title'] for e in b.get('/api/events').json())
    assert b.post('/api/actions/'+action['id']+'/confirm',json={}).status_code in (403,404)


def test_teacher_documents_have_separate_files_and_cleanup_is_scoped(full):
    app,connect,base=full;a,_=connect();b,_=connect()
    da=next(d for d in a.get('/api/documents').json() if d['owner_id']==a.user['id']);dbb=next(d for d in b.get('/api/documents').json() if d['owner_id']==b.user['id'])
    assert 'storage_key' not in da and 'storage_key' not in dbb
    assert a.get('/api/documents/'+da['id']+'/download').status_code==200
    assert b.get('/api/documents/'+da['id']+'/download').status_code==404
    assert a.delete('/api/documents/'+da['id']).status_code in (200,204)
    assert b.get('/api/documents/'+dbb['id']+'/download').status_code==200
    cid=a.user['center_id'];assert a.post('/api/teacher-demo/end').status_code==200
    with app.state.session_factory() as db:
        assert db.get(Center,cid) is None and db.get(User,a.user['id']) is None
        assert db.get(Center,base) and db.get(Center,b.user['center_id'])
    assert b.get('/api/academic').status_code==200
    assert b.get('/api/documents/'+dbb['id']+'/download').status_code==200


def test_full_profile_denies_admin_credentials_and_account_registration(full):
    app,connect,base=full;c,r=connect()
    cookie=r.headers['set-cookie'].lower();assert all(x in cookie for x in ['secure','httponly','samesite=strict','max-age=86400'])
    c.headers.pop('x-csrf-token');assert c.post('/api/conversations',json={}).status_code==403
    c.headers['x-csrf-token']=r.json()['csrf_token']
    for path in ['/api/admin/users','/api/demo-launch/status','/api/operations/diagnostics','/api/docs','/api/openapi.json','/.env','/data/axon.sqlite3']:
        assert c.get(path).status_code==403,path
    for path in ['/api/auth/login','/api/auth/password','/api/account/setup','/api/integrations/classroom/authorize','/api/ai/public-prompt']:
        assert c.post(path,json={}).status_code==403,path
    assert c.post('/api/conversations',headers={'Origin':'https://other.example'},json={}).status_code==403
    assert c.get('/api/public/info',headers={'Host':'teacher-fixture.trycloudflare.com'}).status_code==403
    info=c.get('/api/public/info').json();assert info['full_demo'] and info['teacher_session_hours']==24


def test_session_24_hours_does_not_expire_after_five_and_profile_rejects_personal(full):
    app,connect,base=full;c,_=connect()
    with app.state.session_factory() as db:
        row=db.scalar(select(TeacherDemoSession).where(TeacherDemoSession.user_id==c.user['id']))
        assert row.expires_at>utcnow()+timedelta(hours=23)
        row.created_at=utcnow()-timedelta(hours=6);db.commit()
        teacher_demo.validate_profile(app.state.settings,db)
        user=db.get(User,c.user['id']);user.is_demo=False
        with pytest.raises(ValueError,match='personal'):teacher_demo.validate_profile(app.state.settings,db)
        db.rollback()
    assert c.get('/api/teacher-demo/status').status_code==200
    with app.state.session_factory() as db:
        db.execute(update(TeacherDemoSession).where(TeacherDemoSession.user_id==c.user['id']).values(expires_at=utcnow()-timedelta(seconds=1)));db.commit()
    assert c.get('/api/academic').status_code==401
    with app.state.session_factory() as db:teacher_demo.cleanup(db,app.state.settings);assert db.get(User,c.user['id']) is None


def test_teacher_upload_export_and_query_limits_are_per_session(full):
    from app.models import GuestRate
    from app.auth import digest
    app,connect,base=full;a,_=connect();b,_=connect()
    result=a.post('/api/documents',data={'title':'Texto del profesor ficticio'},files={'file':('profesor.txt',b'Ejemplo propio de fracciones para practicar.','text/plain')})
    assert result.status_code==201,result.text
    ident=result.json()['id']
    assert b.get('/api/documents/'+ident+'/download').status_code==404
    exported=a.get('/api/profile/export');assert exported.status_code==200,exported.text
    assert ident in str(exported.json()) and b.user['id'] not in str(exported.json())
    with app.state.session_factory() as db:
        row=db.scalar(select(TeacherDemoSession).where(TeacherDemoSession.user_id==a.user['id']))
        # A's exhausted hourly allowance must not block B on the same IP.
        for _ in range(100):db.add(GuestRate(key_hash=digest('teacher-query-hour:'+row.id)))
        db.commit()
    denied=a.post('/api/voice/speech',json={'text':'Hola'});assert denied.status_code==429
    assert b.post('/api/tools/call',json={'tool':'query_subjects','arguments':{}}).status_code==200
    assert a.post('/api/teacher-demo/end').status_code==200


def test_three_demo_roles_share_one_fictional_school_but_keep_permissions(tmp_path):
    from dataclasses import replace
    from fastapi.testclient import TestClient
    from app.config import Settings
    from app.teacher_prepare import prepare
    from app.main import create_app
    import json
    settings=replace(Settings.from_env(),data_dir=tmp_path/'demo',database_url=f'sqlite:///{tmp_path}/demo/axon.sqlite3',
        demo=True,public_demo=True,full_demo=True,remote_demo=False,cookie_secure=True,
        public_origin_host='axon-'+'a'*64+'.localhost',ai_mode='simulated')
    # Build the template without copying any institution or personal data.
    from app.db import create_db
    from app.seed import seed_demo
    from app.atlas import bootstrap
    from app.nebula import populate
    from app.models import User,Center
    from sqlalchemy import select
    settings.data_dir.mkdir()
    (settings.data_dir/'uploads').mkdir()
    from app.main import migrate
    migrate(settings)
    engine,factory=create_db(settings.database_url)
    with factory() as db:
        seed_demo(db,settings)
        center=db.scalar(select(Center))
        populate(db,settings,center.id)
        bootstrap(db)
        for user in db.scalars(select(User)):
            user.active=False
            user.password_hash=''
        db.commit()
        center_id=center.id
    engine.dispose()
    (settings.data_dir/'remote-demo.json').write_text(json.dumps({'profile':'teacher-fictitious-v1','center_id':center_id,'personal_data_copied':False}))
    (settings.data_dir/'quick-runtime.json').write_text(json.dumps({'enabled':True,'hostname':'nebula-tests.trycloudflare.com'}))
    app=create_app(settings,maintenance=False)
    with TestClient(app,base_url='https://'+settings.public_origin_host) as client:
        client.headers['Origin']='https://nebula-tests.trycloudflare.com'
        start=client.post('/api/teacher-demo/start',json={'role':'admin'})
        assert start.status_code==200,start.text
        identity=start.json()
        assert identity['user']['role']=='admin'
        center=identity['user']['center_id']
        client.headers['X-CSRF-Token']=identity['csrf_token']
        assert client.get('/api/admin/users').status_code==200
        assert client.get('/api/admin/operations/diagnostics').status_code==403
        classes=client.get('/api/classes').json()['classes']
        assert len(classes)==108
        for role in ('teacher','student','admin'):
            response=client.post('/api/teacher-demo/perspective',json={'role':role})
            assert response.status_code==200,response.text
            payload=response.json()
            assert payload['user']['center_id']==center and payload['user']['role']==role
            client.headers['X-CSRF-Token']=payload['csrf_token']
            assert client.get('/api/admin/users').status_code==(200 if role=='admin' else 403)
            from app.teacher_demo import validate_profile
            with app.state.session_factory() as db:
                validate_profile(settings,db)
        assert client.post('/api/teacher-demo/end').status_code==200
