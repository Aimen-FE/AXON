from conftest import DEMO_PASSWORDS
"""Remote is tested with fictitious data, local signing keys and no cloud calls."""
import json,time
from datetime import timedelta
from dataclasses import replace
import jwt,pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from sqlalchemy import select
from app.config import Settings
from app.main import create_app
from app.models import User,Center,RemoteInvitation,Session
from app.remote import issue
from app.auth import ph
from app.db import utcnow

@pytest.fixture
def remote(tmp_path):
    local=replace(Settings.from_env(),data_dir=tmp_path,database_url=f'sqlite:///{tmp_path}/remote.sqlite3',demo=True,remote_demo=False,ai_mode='simulated')
    seed=create_app(local,maintenance=False,demo_passwords={})
    with seed.state.session_factory() as db:
        center=db.scalar(select(Center));owner=db.scalar(select(User).where(User.username=='admin.demo'));teacher=db.scalar(select(User).where(User.username=='profesor.demo'));student=db.scalar(select(User).where(User.username=='alumno.demo'))
        for u in db.scalars(select(User)):u.active=False;u.password_hash=''
        owner_id,teacher_id,student_id=owner.id,teacher.id,student.id
        token=issue(db,teacher,'teacher@example.test',24);issue(db,owner,'owner@example.test',24);issue(db,student,'student@example.test',24)
        owner_invite=db.scalar(select(RemoteInvitation).where(RemoteInvitation.user_id==owner.id));owner_invite.consumed=True;owner.active=True;owner.password_hash=ph.hash('FictitiousOwner!2030')
        db.commit();(tmp_path/'remote-demo.json').write_text(json.dumps({'profile':'atlas-fictitious-v1','center_id':center.id}))
    seed.state.engine.dispose()
    settings=replace(local,remote_demo=True,cookie_secure=True,public_hostname='atlas.example.test',allowed_origins=('https://atlas.example.test',),access_issuer='https://atlas-tests.cloudflareaccess.com',access_audience='fictitious-atlas-audience')
    app=create_app(settings,maintenance=False);key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    app.state.access_verifier.keys={'fixture':key.public_key()};app.state.access_verifier.loaded=time.monotonic()
    def signed(subject_email,**changes):
        payload={'iss':settings.access_issuer,'aud':settings.access_audience,'sub':'fixture-'+subject_email,'email':subject_email,'iat':int(time.time())-2,'exp':int(time.time())+600};payload.update(changes)
        return jwt.encode(payload,key,algorithm='RS256',headers={'kid':'fixture'})
    with TestClient(app,base_url='https://atlas.example.test') as client:
        yield client,app,signed,token,(owner_id,teacher_id,student_id)
    app.state.engine.dispose()

def auth(client,signed):
    client.headers['cf-access-jwt-assertion']=signed('owner@example.test')
    r=client.post('/api/auth/login',json={'username':'admin.demo','password':'FictitiousOwner!2030'});assert r.status_code==200,r.text
    client.headers['x-csrf-token']=r.json()['csrf_token'];return r

def test_access_signature_claims_all_paths_and_secure_session(remote):
    c,app,signed,token,ids=remote
    assert c.get('/').status_code==403
    for changes in ({'aud':'wrong'},{'iss':'https://other.cloudflareaccess.com'},{'exp':int(time.time())-20},{'email':'uninvited@example.test'}):
        c.headers['cf-access-jwt-assertion']=signed('owner@example.test',**changes)
        assert c.get('/api/health').status_code==403
    r=auth(c,signed);cookie=r.headers['set-cookie'].lower();assert 'secure' in cookie and 'httponly' in cookie and 'samesite=strict' in cookie
    c.headers['cf-access-jwt-assertion']=signed('student@example.test')
    assert c.get('/api/conversations').status_code==403
    c.headers['cf-access-jwt-assertion']=signed('owner@example.test')
    c.headers.pop('x-csrf-token');assert c.post('/api/conversations',json={}).status_code==403

def test_invitation_is_individual_expiring_one_use_and_revocable(remote):
    c,app,signed,token,ids=remote
    c.headers['cf-access-jwt-assertion']=signed('student@example.test')
    assert c.post('/api/remote/accept',json={'token':token,'password':'FictitiousTeacher!2030'}).status_code==403
    c.headers['cf-access-jwt-assertion']=signed('teacher@example.test')
    r=c.post('/api/remote/accept',json={'token':token,'password':'FictitiousTeacher!2030'});assert r.status_code==200,r.text
    assert c.post('/api/remote/accept',json={'token':token,'password':'FictitiousTeacher!2030'}).status_code==403
    r=c.post('/api/auth/login',json={'username':'profesor.demo','password':'FictitiousTeacher!2030'});assert r.status_code==200
    c.headers['x-csrf-token']=r.json()['csrf_token']
    convo=c.post('/api/conversations',json={'title':'Solo docente ficticio'}).json()['id']
    assert c.get('/api/atlas/core').status_code==200
    assert c.post('/api/admin/users',json={}).status_code in (403,422)
    auth(c,signed)
    assert c.get('/api/conversations/'+convo).status_code==404
    created=c.post('/api/admin/users',json={'username':'otro.ficticio','display_name':'Otro ficticio','password':'OtroFicticio!2030','role':'teacher','group_ids':[]});assert created.status_code==409
    assert c.post('/api/remote/revoke/'+ids[1]).status_code==200
    assert c.patch('/api/admin/users/'+ids[1],json={'active':True}).status_code==409
    with app.state.session_factory() as db:
        assert not db.scalar(select(Session.id).where(Session.user_id==ids[1]))
    c.headers['cf-access-jwt-assertion']=signed('teacher@example.test')
    assert c.get('/api/health').status_code==403

def test_start_refuses_shared_passwords_and_nonisolated_data(tmp_path):
    settings=replace(Settings.from_env(),data_dir=tmp_path,database_url=f'sqlite:///{tmp_path}/test.sqlite3',demo=True,remote_demo=True,cookie_secure=True,public_hostname='atlas.example.test',allowed_origins=('https://atlas.example.test',),access_issuer='https://atlas-tests.cloudflareaccess.com',access_audience='fictitious-atlas-audience')
    with pytest.raises(ValueError,match='ficticia'):create_app(settings,maintenance=False)
    local=create_app(replace(settings,remote_demo=False),maintenance=False,demo_passwords=DEMO_PASSWORDS)
    with local.state.session_factory() as db:(tmp_path/'remote-demo.json').write_text(json.dumps({'profile':'atlas-fictitious-v1','center_id':db.scalar(select(Center.id))}))
    local.state.engine.dispose()
    with pytest.raises(ValueError,match='invitación individual'):create_app(settings,maintenance=False)

def test_fictitious_uploads_survive_profile_validation_but_personal_accounts_do_not(remote):
    c,app,signed,token,ids=remote;auth(c,signed)
    response=c.post('/api/documents',data={'title':'Apuntes ficticios del ensayo'},files={'file':('ficticio.txt',b'Contenido inventado para la demostracion','text/plain')});assert response.status_code==201
    from app.remote import validate_profile
    with app.state.session_factory() as db:
        validate_profile(app.state.settings,db)
        private=User(center_id=db.get(User,ids[0]).center_id,username='privado.prohibido',display_name='Cuenta de prueba privada',password_hash='',active=False,is_demo=False,role='student');db.add(private);db.flush()
        with pytest.raises(ValueError,match='personales'):validate_profile(app.state.settings,db)
