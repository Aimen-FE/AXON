from datetime import timedelta
from sqlalchemy import select
from app.models import ActionRequest,User,CalendarEvent,AuditLog
from app.db import utcnow
from conftest import exam_args
from test_memory_chat import send


def propose(c,tool,args):
    r=c.post('/api/tools/call',json={'tool':tool,'arguments':args})
    assert r.status_code==200,r.text
    return r.json()


def test_exam_proposal_confirmation_student_visibility_and_idempotency(login):
    teacher,student,other=login('profesor.demo'),login(),login('alumno2.demo')
    p=propose(teacher,'publish_exam',exam_args(teacher))
    aid=p['action']['id'];assert p['status']=='pending_confirmation'
    assert not any(e['title']=='Examen de regresión' for e in student.get('/api/events').json())
    assert student.post('/api/actions/'+aid+'/confirm').status_code==404
    r=teacher.post('/api/actions/'+aid+'/confirm');assert r.status_code==200,r.text
    ident=r.json()['result']['id']
    assert teacher.post('/api/actions/'+aid+'/confirm').json()['result']['id']==ident
    assert any(e['id']==ident for e in student.get('/api/events').json())
    assert not any(e['id']==ident for e in other.get('/api/events').json())
    assert any(n['title']=='Examen de regresión' for n in student.get('/api/notifications').json())


def test_confirmation_rechecks_conflicts_and_rolls_back(login):
    c=login('profesor.demo');args=exam_args(c)
    a=propose(c,'publish_exam',args)['action'];b=propose(c,'publish_exam',dict(args,title='Segundo examen'))['action']
    assert c.post('/api/actions/'+a['id']+'/confirm').status_code==200
    r=c.post('/api/actions/'+b['id']+'/confirm')
    assert r.status_code==409
    pending=next(x for x in c.get('/api/actions').json() if x['id']==b['id'])
    assert pending['status']=='pending'
    assert not any(e['title']=='Segundo examen' for e in c.get('/api/events').json())


def test_permission_revocation_expiry_and_rejection(app,login):
    from app.models import Teaching
    from sqlalchemy import delete
    c=login('profesor.demo')
    a=propose(c,'publish_exam',exam_args(c))['action']
    with app.state.session_factory() as db:
        db.execute(delete(Teaching).where(Teaching.teacher_id==c.user['id']))
        db.commit()
    assert c.post('/api/actions/'+a['id']+'/confirm').status_code in (403,404)
    admin=login('admin.demo');a=propose(admin,'publish_exam',exam_args(admin))['action']
    with app.state.session_factory() as db:
        obj=db.get(ActionRequest,a['id']);obj.expires_at=utcnow()-timedelta(seconds=1);db.commit()
    assert admin.post('/api/actions/'+a['id']+'/confirm').status_code==409
    b=propose(admin,'publish_exam',exam_args(admin,title='Descartado'))['action']
    assert admin.post('/api/actions/'+b['id']+'/reject').status_code==200
    assert admin.post('/api/actions/'+b['id']+'/confirm').status_code==409


def test_event_edit_cancel_and_optimistic_version(login):
    c=login('profesor.demo');a=propose(c,'publish_exam',exam_args(c))['action']
    event=c.post('/api/actions/'+a['id']+'/confirm').json()['result']
    update=propose(c,'update_event',{'event_id':event['id'],'version':1,'starts_at':'2030-12-19T11:00:00+01:00','ends_at':'2030-12-19T12:00:00+01:00'})['action']
    assert c.post('/api/actions/'+update['id']+'/confirm').status_code==200
    assert c.post('/api/tools/call',json={'tool':'cancel_event','arguments':{'event_id':event['id'],'version':1}}).status_code==409
    cancel=propose(c,'cancel_event',{'event_id':event['id'],'version':2})['action']
    assert c.post('/api/actions/'+cancel['id']+'/confirm').json()['result']['status']=='cancelled'


def test_personal_event_preferences_and_isolation(login):
    c=login();other=login('alumna.demo')
    args={'title':'Mi repaso privado','starts_at':'2030-12-18T16:00:00+01:00','ends_at':'2030-12-18T17:00:00+01:00','visibility':'personal','kind':'reminder'}
    r=propose(c,'create_event',args);assert r['status']=='completed'
    assert not any(e['title']=='Mi repaso privado' for e in other.get('/api/events').json())
    assert c.patch('/api/auth/preferences',json={'theme':'dark','notifications':{},'automatic_personal_actions':False}).status_code==200
    args['starts_at']='2030-12-18T18:00:00+01:00';args['ends_at']='2030-12-18T19:00:00+01:00'
    assert propose(c,'create_event',args)['status']=='pending_confirmation'


def test_natural_language_exam_and_missing_time(login):
    c=login('profesor.demo');convo=c.post('/api/conversations',json={}).json()['id']
    r=send(c,convo,'Programa un examen de Matemáticas para 1.º Bachillerato A el 19 de diciembre de 2030 a las 09:00')
    actions=r['assistant_message']['details']['actions'];assert len(actions)==1
    assert actions[0]['tool']=='publish_exam'
    assert c.post('/api/actions/'+actions[0]['id']+'/confirm').status_code==200
    r=send(c,convo,'Programa un examen de Matemáticas para 1.º Bachillerato A el 20 de diciembre de 2030','natural-0002')
    assert 'hora' in r['assistant_message']['content']
    assert not r['assistant_message']['details']['actions']
    r=send(c,convo,'a las 12:00','natural-0003')
    assert r['assistant_message']['details']['actions']


def test_assignment_publication_submission_and_other_student_privacy(login):
    teacher,student,other=login('profesor.demo'),login(),login('alumna.demo')
    args=exam_args(teacher)
    a=propose(teacher,'create_assignment',{'title':'Tarea de prueba','description':'Responde','group_id':args['group_id'],'subject_id':args['subject_id'],'due_at':'2030-12-18T20:00:00+01:00'})['action']
    task=teacher.post('/api/actions/'+a['id']+'/confirm').json()['result']
    tid=task['id']
    assert student.put(f'/api/assignments/{tid}/submission',json={'content':'Respuesta privada','status':'submitted'}).status_code==200
    assert student.get(f'/api/assignments/{tid}/submissions').status_code==403
    assert other.get(f'/api/assignments/{tid}/submissions').status_code==403
    assert teacher.get(f'/api/assignments/{tid}/submissions').json()[0]['content']=='Respuesta privada'
    assert next(a for a in other.get('/api/assignments').json() if a['id']==tid)['submission'] is None


def test_schedule_csv_and_overlap_validation(login):
    c=login('profesor.demo')
    text='group,subject,teacher,weekday,starts,ends,classroom\n1.º Bachillerato A,Matemáticas,profesor.demo,4,17:00,18:00,Aula 101\n'
    p=c.post('/api/schedules/import',files={'file':('horario.csv',text.encode(),'text/csv')})
    assert p.status_code==200,p.text
    aid=p.json()['action']['id'];assert c.post('/api/actions/'+aid+'/confirm').status_code==200
    p=c.post('/api/schedules/import',files={'file':('horario.csv',text.encode(),'text/csv')})
    assert p.json()['conflicts']
    assert c.post('/api/actions/'+p.json()['action']['id']+'/confirm').status_code==409


def test_invalid_dates_and_calendar_foreign_edit(login):
    c=login('profesor.demo');student=login()
    assert c.post('/api/tools/call',json={'tool':'publish_exam','arguments':exam_args(c,ends_at='2030-12-19T08:00:00+01:00')}).status_code==422
    event=next(e for e in student.get('/api/events').json() if e['kind']=='exam')
    assert student.post('/api/tools/call',json={'tool':'cancel_event','arguments':{'event_id':event['id'],'version':event['version']}}).status_code==403


def test_date_filters_are_validated_on_all_query_tools(login):
    c=login()
    for name in ('query_schedule','query_assignments','query_exams'):
        assert c.post('/api/tools/call',json={'tool':name,'arguments':{'day':'2026-02-30'}}).status_code==422


def test_assignment_update_requires_confirmation_and_prevents_stale_changes(login):
    c=login('profesor.demo');a=next(x for x in c.get('/api/assignments').json() if 'funciones' in x['title'])
    args={'assignment_id':a['id'],'expected_updated_at':a['updated_at'],'due_at':'2030-12-20T20:00:00+01:00','title':'Tarea corregida'}
    pending=propose(c,'update_assignment',args)['action']
    assert next(x for x in c.get('/api/assignments').json() if x['id']==a['id'])['title']!=args['title']
    assert c.post('/api/actions/'+pending['id']+'/confirm').status_code==200
    assert c.post('/api/tools/call',json={'tool':'update_assignment','arguments':args}).status_code==409


def test_schedule_edit_delete_and_ownership(login):
    c=login('profesor.demo');other=login('profesora.demo')
    session=next(s for s in c.get('/api/schedules').json() if s['teacher_id']==c.user['id'])
    args={'schedule_id':session['id'],'expected_updated_at':session['updated_at'],'weekday':session['weekday'],'starts':'18:00','ends':'19:00','classroom_id':session['classroom_id']}
    assert other.post('/api/tools/call',json={'tool':'update_schedule','arguments':args}).status_code==403
    action=propose(c,'update_schedule',args)['action']
    assert c.post('/api/actions/'+action['id']+'/confirm').status_code==200
    updated=next(s for s in c.get('/api/schedules').json() if s['id']==session['id'])
    action=propose(c,'delete_schedule',{'schedule_id':updated['id'],'expected_updated_at':updated['updated_at']})['action']
    assert c.post('/api/actions/'+action['id']+'/confirm').json()['result']['removed']
    assert not any(s['id']==updated['id'] for s in c.get('/api/schedules').json())
