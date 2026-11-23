from conftest import DEMO_TEST_PASSWORD
from datetime import timedelta
from fastapi.testclient import TestClient
from sqlalchemy import select
from app.auth import ph,COOKIE
from app.models import User,Session,Center,Group,Course,AcademicYear,Enrollment
from app.db import utcnow
from conftest import exam_args


def test_authentication_cookie_logout_and_invalid_password(app,login):
    c=TestClient(app)
    assert c.get('/api/academic').status_code==401
    assert c.post('/api/auth/login',json={'username':'alumno.demo','password':'bad'}).status_code==401
    s=login()
    me=s.get('/api/auth/me')
    assert me.status_code==200
    assert 'password_hash' not in me.text
    assert 'httponly' in s.cookies.jar._cookies['testserver.local']['/'][COOKIE]._rest.keys() or any(k.lower()=='httponly' for k in s.cookies.jar._cookies['testserver.local']['/'][COOKIE]._rest)
    assert s.post('/api/auth/logout').status_code==200
    assert s.get('/api/academic').status_code==401


def test_password_is_argon2_and_no_raw_session_token(app,login):
    c=login()
    with app.state.session_factory() as db:
        u=db.scalar(select(User).where(User.username=='alumno.demo'))
        assert u.password_hash.startswith('$argon2id$')
        assert ph.verify(u.password_hash,DEMO_TEST_PASSWORD)
        session=db.scalar(select(Session).where(Session.user_id==u.id))
        assert session.token_hash!=c.cookies.get(COOKIE)


def test_expired_and_disabled_sessions(app,login):
    c=login()
    with app.state.session_factory() as db:
        s=db.scalar(select(Session).where(Session.user_id==c.user['id']))
        s.expires_at=utcnow()-timedelta(seconds=1);db.commit()
    assert c.get('/api/academic').status_code==401
    c=login()
    admin=login('admin.demo')
    assert admin.patch('/api/admin/users/'+c.user['id'],json={'active':False}).status_code==200
    assert c.get('/api/academic').status_code==401


def test_csrf_origin_host_and_security_headers(login):
    c=login();token=c.headers.pop('x-csrf-token')
    assert c.post('/api/memory',json={'content':'No debe guardarse'}).status_code==403
    c.headers['x-csrf-token']=token
    assert c.post('/api/memory',json={'content':'No debe guardarse'},headers={'Origin':'https://evil.test'}).status_code==403
    assert c.get('/api/health',headers={'Host':'evil.test'}).status_code==400
    r=c.get('/api/memory')
    assert r.headers['cache-control']=='no-store'
    assert r.headers['x-content-type-options']=='nosniff'
    assert r.headers['x-frame-options']=='DENY'


def test_login_rate_limit(app):
    c=TestClient(app)
    for _ in range(8):assert c.post('/api/auth/login',json={'username':'missing.demo','password':'wrong'}).status_code==401
    r=c.post('/api/auth/login',json={'username':'missing.demo','password':'wrong'})
    assert r.status_code==429
    assert r.headers['retry-after']=='600'


def test_roles_cannot_use_staff_or_admin_routes(login):
    c=login()
    for path in ['/api/bathroom','/api/reports','/api/admin/users','/api/admin/audit']:
        assert c.get(path).status_code==403
    assert c.post('/api/tools/call',json={'tool':'publish_exam','arguments':exam_args(c)}).status_code==403
    teacher=login('profesor.demo')
    assert teacher.get('/api/admin/users').status_code==403
    assert teacher.post('/api/tools/call',json={'tool':'prepare_report','arguments':{}}).status_code==403


def test_student_and_admin_cannot_read_other_private_conversations(login):
    a,b,admin=login(),login('alumna.demo'),login('admin.demo')
    convo=a.post('/api/conversations',json={}).json()['id']
    assert a.post('/api/conversations/'+convo+'/messages',json={'content':'Recuerda mi palabra privada quetzal','client_id':'privacy-0001'}).status_code==200
    for other in (b,admin):
        assert other.get('/api/conversations/'+convo).status_code==404
        assert other.post('/api/conversations/'+convo+'/messages',json={'content':'Hola','client_id':'privacy-0002'}).status_code==404
        result=other.get('/api/memory?q=quetzal').json()
        assert result=={'memories':[],'messages':[]}
        assert 'quetzal' not in other.get('/api/profile/export').text


def test_teacher_scope_subject_and_cross_center(login,app):
    teacher=login('profesor.demo');other=login('profesora.demo')
    assert other.post('/api/tools/call',json={'tool':'publish_exam','arguments':exam_args(teacher)}).status_code==403
    with app.state.session_factory() as db:
        center=Center(name='Otro centro ficticio');db.add(center);db.flush()
        year=AcademicYear(center_id=center.id,name='2030');db.add(year);db.flush()
        course=Course(center_id=center.id,year_id=year.id,name='Otro',stage='ESO');db.add(course);db.flush()
        group=Group(center_id=center.id,course_id=course.id,name='Grupo externo');db.add(group);db.flush();gid=group.id
        db.commit()
    r=teacher.post('/api/tools/call',json={'tool':'publish_exam','arguments':exam_args(teacher,group_id=gid)})
    assert r.status_code==404
    assert teacher.get('/api/groups/'+gid+'/students').status_code==404


def test_unknown_tools_and_extra_arguments_rejected(login):
    c=login('profesor.demo')
    assert c.post('/api/tools/call',json={'tool':'run_shell','arguments':{'command':'ls'}}).status_code==404
    assert c.post('/api/tools/call',json={'tool':'query_exams','arguments':{'command':'ls'}}).status_code==422
    assert c.post('/api/tools/call',json={'tool':'create_event','arguments':exam_args(c,starts_at='2030-01-01T09:00:00',ends_at='2030-01-01T10:00:00')} ).status_code==422
