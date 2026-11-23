from conftest import DEMO_TEST_PASSWORD
from datetime import timedelta
from sqlalchemy import select,func
from app.db import utcnow
from app.models import User,Memory,Conversation,Message,Document,CalendarEvent,BathroomPass,ReviewReport,ActionRequest
from app.reports import daily_maintenance
from conftest import exam_args
from test_academic import propose
from test_documents import upload
from test_memory_chat import send


def student_group(teacher,student):
    meta=teacher.get('/api/academic').json()
    return next(g for g in meta['groups'] if g['id'] in student.user['group_ids'])


def test_bathroom_register_return_duplicates_scope_and_audit(login):
    teacher,student,outsider=login('profesor.demo'),login(),login('alumno2.demo')
    g=student_group(teacher,student)
    body={'student_id':student.user['id'],'group_id':g['id']}
    r=teacher.post('/api/bathroom',json=body);assert r.status_code==201,r.text
    ident=r.json()['id']
    assert teacher.post('/api/bathroom',json=body).status_code==409
    assert teacher.post('/api/bathroom',json={'student_id':outsider.user['id'],'group_id':g['id']}).status_code==404
    assert student.get('/api/bathroom').status_code==403
    assert student.post(f'/api/bathroom/{ident}/return').status_code in (403,404)
    r=teacher.post(f'/api/bathroom/{ident}/return');assert r.status_code==200
    assert r.json()['returned_at']
    assert teacher.post(f'/api/bathroom/{ident}/return').json()['returned_at']==r.json()['returned_at']
    logs=login('admin.demo').get('/api/admin/audit').json()
    assert any(x['operation']=='bathroom_out' for x in logs)
    assert all('content' not in x['details'] for x in logs)


def test_natural_bathroom_register_and_return(login):
    c=login('profesor.demo');convo=c.post('/api/conversations',json={}).json()['id']
    r=send(c,convo,'Registra la salida al baño de Teo Cúmulo de 2.º B')['assistant_message']
    assert r['details']['tools'][0]['name']=='register_bathroom',r
    assert 'registrada' in r['content']
    r=send(c,convo,'Registra el regreso del baño de Teo Cúmulo de 2.º B','return-0002')['assistant_message']
    assert r['details']['tools'][0]['name']=='return_bathroom'


def test_report_excludes_private_data_and_acceptance_requires_confirmation(login):
    student,admin=login(),login('admin.demo')
    student.post('/api/memory',json={'content':'Privado cienfuegos'})
    convo=student.post('/api/conversations',json={}).json()['id'];send(student,convo,'Recuerda el secreto cienfuegos')
    upload(student,'privado.txt',b'cienfuegos: contenido personal')
    report=admin.post('/api/reports').json()
    assert 'cienfuegos' not in str(report)
    assert any(f['kind']=='missing' for f in report['findings'])
    finding=next(f for f in report['findings'] if f['kind']=='validation')
    r=admin.post(f'/api/reports/{report["id"]}/findings/{finding["id"]}',json={'decision':'accepted'})
    assert r.status_code==200,r.text
    action=r.json()['action'];assert action['status']=='pending'
    assert admin.post('/api/actions/'+action['id']+'/confirm').status_code==200
    report2=admin.post('/api/reports').json()
    assert not any(f['kind']=='validation' for f in report2['findings'])
    assert any('biblioteca' in d['title'].lower() for d in student.get('/api/documents').json())


def test_daily_review_is_idempotent_and_prunes_only_expired_passes(app,login):
    teacher,student=login('profesor.demo'),login();g=student_group(teacher,student)
    with app.state.session_factory() as db:
        old=BathroomPass(center_id=teacher.user['center_id'],student_id=student.user['id'],group_id=g['id'],recorded_by=teacher.user['id'],left_at=utcnow()-timedelta(days=20),returned_at=utcnow()-timedelta(days=20,hours=-1))
        db.add(old);db.commit();ident=old.id
        messages=db.scalar(select(func.count()).select_from(Message))
        daily_maintenance(db);daily_maintenance(db)
        assert db.get(BathroomPass,ident) is None
        assert db.scalar(select(func.count()).select_from(ReviewReport).where(ReviewReport.trigger=='scheduled'))==1
        assert db.scalar(select(func.count()).select_from(Message))==messages


def test_notification_preferences_and_cross_user_read(login):
    student,teacher,other=login(),login('profesor.demo'),login('alumna.demo')
    assert student.patch('/api/auth/preferences',json={'notifications':{'exam':False}}).status_code==200
    a=propose(teacher,'publish_exam',exam_args(teacher))['action'];teacher.post('/api/actions/'+a['id']+'/confirm')
    assert not any(n['title']=='Examen de regresión' for n in student.get('/api/notifications').json())
    n=next(n for n in other.get('/api/notifications').json() if n['title']=='Examen de regresión')
    assert student.patch('/api/notifications/'+n['id']+'/read').status_code==404
    assert other.patch('/api/notifications/'+n['id']+'/read').json()['read'] is True


def test_portability_and_personal_erasure(login,app):
    admin=login('admin.demo')
    group=admin.get('/api/academic').json()['groups'][0]['id']
    r=admin.post('/api/admin/users',json={'username':'erase.demo','display_name':'Alumno Borrado Demo','role':'student','password':DEMO_TEST_PASSWORD,'group_ids':[group]})
    assert r.status_code==201,r.text
    c=login('erase.demo');ident=c.user['id']
    c.post('/api/memory',json={'content':'Mis datos efímeros'})
    convo=c.post('/api/conversations',json={}).json()['id'];send(c,convo,'Recuerda efímero')
    upload(c,'datos.txt',b'Datos personales ficticios')
    exported=c.get('/api/profile/export');assert exported.status_code==200
    assert 'efímeros' in exported.text
    assert 'password_hash' not in exported.text and 'csrf_token' not in exported.text
    assert c.request('DELETE','/api/profile/data',json={'password':'bad','confirmation':'ELIMINAR MIS DATOS'}).status_code==403
    r=c.request('DELETE','/api/profile/data',json={'password':DEMO_TEST_PASSWORD,'confirmation':'ELIMINAR MIS DATOS'})
    assert r.status_code==200,r.text
    assert c.get('/api/auth/me').status_code==401
    with app.state.session_factory() as db:
        u=db.get(User,ident);assert not u.active and u.display_name=='Cuenta eliminada'
        assert not db.scalar(select(Memory).where(Memory.user_id==ident))
        assert not db.scalar(select(Conversation).where(Conversation.user_id==ident))
        assert not db.scalar(select(Document).where(Document.owner_id==ident))


def test_admin_cannot_erase_last_admin_or_deactivate_self(login):
    admin=login('admin.demo')
    assert admin.patch('/api/admin/users/'+admin.user['id'],json={'active':False}).status_code==422
    assert admin.request('DELETE','/api/profile/data',json={'password':DEMO_TEST_PASSWORD,'confirmation':'ELIMINAR MIS DATOS'}).status_code==409


def test_public_kiosk_endpoint_contains_no_accounts_or_private_records(app,login):
    c=login();response=c.get('/api/public/info');assert response.status_code==200
    body=response.json();assert set(body).issubset({'center','demo','remote_demo','public_demo','guest_duration_minutes','guest_queries','documents'})
    assert 'user' not in body and 'conversations' not in body


def test_frontend_and_pwa_assets_are_served(login):
    c=login()
    root=c.get('/');assert root.status_code==200 and '<div id="root">' in root.text
    manifest=c.get('/manifest.webmanifest').json()
    assert manifest['display']=='standalone' and manifest['name']=='AXON' and manifest['short_name']=='AXON'
    assert {'any','maskable'} <= {icon['purpose'] for icon in manifest['icons']}
    for icon in manifest['icons']:
        asset=c.get(icon['src'])
        assert asset.status_code==200 and asset.headers['content-type'].startswith('image/png')
    worker=c.get('/sw.js')
    assert worker.status_code==200 and worker.headers['cache-control']=='no-cache'
    assert c.get('/offline.html').status_code==200
    assert c.get('/api/missing').status_code==404


def test_admin_can_expand_structure_and_enroll_students(login):
    admin=login('admin.demo');student=login()
    year=admin.post('/api/admin/structure',json={'kind':'year','name':'2030–2031'})
    assert year.status_code==201
    course=admin.post('/api/admin/structure',json={'kind':'course','name':'3.º ESO','year_id':year.json()['id'],'stage':'ESO'})
    assert course.status_code==201
    group=admin.post('/api/admin/groups',json={'course_id':course.json()['id'],'name':'3.º ESO C'})
    assert group.status_code==201
    enrollment=admin.post('/api/admin/enrollments',json={'student_id':student.user['id'],'group_id':group.json()['id']})
    assert enrollment.status_code==201
    assert any(g['id']==group.json()['id'] for g in student.get('/api/academic').json()['groups'])
    assert admin.post('/api/admin/structure',json={'kind':'subject','name':'Tecnología','color':'#123456'}).status_code==201
    assert student.post('/api/admin/structure',json={'kind':'subject','name':'Indebida'}).status_code==403
