import io,secrets
from datetime import timedelta
from decimal import Decimal
from fastapi.testclient import TestClient
from sqlalchemy import select
import pytest
from app.academic_import import provision_bundle,parse_document
from app.models import User,Subject,KnowledgeSource,AssessmentPolicy,AccountSetup,LearnerProfile
from app.auth import digest
from app.db import utcnow
from test_memory_chat import send


@pytest.fixture
def learner(app):
    bundle={'username':'private.test','name':'Estudiante Privado Ficticio','center':'Centro privado de prueba','town':'Localidad ficticia','academic_year':'2026-2027','course':'Bachillerato de prueba','group':'Grupo privado A',
        'subjects':['Matemáticas I','Física y Química','Filosofía','Tecnología e Ingeniería','Inglés'],'additional_subjects':['Digitalización'],'documents':[],'manual':[],'preferences':{'approach':'conceptual'}}
    with app.state.session_factory() as db:
        result=provision_bundle(db,app.state.settings,bundle);uid=result['user_id']
        token=secrets.token_urlsafe(40);setup=db.scalar(select(AccountSetup).where(AccountSetup.user_id==uid));setup.token_hash=digest(token);db.commit()
    with TestClient(app) as c:
        inspect=c.post('/api/onboarding/inspect',json={'token':token});assert inspect.status_code==200
        response=c.post('/api/onboarding/finish',json={'token':token,'password':'Synthetic-Password!2026'})
        assert response.status_code==200,response.text
        c.headers['x-csrf-token']=response.json()['csrf_token'];c.user=response.json()['user'];c.setup_token=token
        yield c


def policy(app,client,scheme='physics',historical=False):
    with app.state.session_factory() as db:
        user=db.get(User,client.user['id']);subjects=list(db.scalars(select(Subject).where(Subject.center_id==user.center_id)))
        names={'physics':'Física y Química','technology':'Tecnología e Ingeniería','english':'Inglés','philosophy':'Filosofía'}
        s=next(x for x in subjects if x.name==names[scheme])
        source=KnowledgeSource(owner_id=user.id,subject_id=s.id,title='Fuente sintética '+scheme,kind=scheme,academic_year='2025-2026' if historical else '2026-2027',applicable_year='2026-2027',verification='historical' if historical else 'pending',warnings=['Fuente histórica'] if historical else [])
        db.add(source);db.flush()
        weights={'physics':{'exams':'90','activities':'5','practical':'5'},'technology':{'participation':'15','projects':'50','exams':'35'},'english':{'listening':'15','speaking':'10','reading':'20','writing':'20','mediation':'5','use_of_english':'25','culture':'5'},'philosophy':{}}[scheme]
        conditions={'recovery_mean':True,'term_rounding':'truncate','final_rounding':'half_up_except_fail','extraordinary_weight':'100'} if scheme=='physics' else {'minimum_skill':'1','minimum_skill_cap':'4'} if scheme=='english' else {'extraordinary_weight':'100'}
        p=AssessmentPolicy(owner_id=user.id,subject_id=s.id,source_id=source.id,scheme=scheme,weights=weights,conditions=conditions,final_weights=['20','40','40'] if scheme=='philosophy' else ['1','2','3'] if scheme=='english' else ['1','1','1'])
        db.add(p);db.commit();return p.id,s.id


def test_setup_one_time_no_default_password_and_student_role(app,learner,login):
    assert learner.user['role']=='student' and not learner.user['is_demo'] and learner.user['has_academic_profile']
    assert learner.post('/api/onboarding/finish',json={'token':learner.setup_token,'password':'Other-Synthetic!2026'}).status_code==404
    admin=login('admin.demo');assert all(u['id']!=learner.user['id'] for u in admin.get('/api/admin/users').json())
    assert learner.get('/api/admin/users').status_code==403
    assert learner.post('/api/onboarding/finish',json={'token':'x'*40,'password':'small'}).status_code==422
    assert 'small' not in learner.post('/api/onboarding/finish',json={'token':'x'*40,'password':'small'}).text


def test_learner_preferences_and_enrollment_are_private(learner,login):
    data=learner.get('/api/learner').json();assert len(data['subject_ids'])==5
    assert not any('Privado' in g['name'] for g in login().get('/api/academic').json()['groups'])
    assert learner.put('/api/learner',json={'preferences':{'response_length':'brief'},'availability':[{'weekday':0,'starts':'17:00','ends':'19:00'}],'subject_ids':data['subject_ids']}).status_code==200
    assert learner.get('/api/learner').json()['profile']['preferences']['response_length']=='brief'


def test_decimal_weighting_and_missing_values(app,learner):
    ident,subject=policy(app,learner)
    result=learner.post('/api/knowledge/calculate',json={'policy_id':ident,'values':{'exams':6,'activities':8,'practical':10}}).json()
    assert Decimal(result['raw'])==Decimal('6.3') and result['grade']=='6' and not result['official']
    assert learner.post('/api/knowledge/calculate',json={'policy_id':ident,'values':{'exams':6}}).json()['status']=='missing_information'
    assert learner.post('/api/knowledge/calculate',json={'policy_id':ident,'values':{'exams':'NaN','activities':8,'practical':10}}).status_code==422
    assert learner.post('/api/knowledge/calculate',json={'policy_id':ident,'simulation':False,'values':{}}).status_code==409


def test_final_special_rules_and_recovery(app,learner):
    ident,_=policy(app,learner)
    result=learner.post('/api/knowledge/calculate',json={'policy_id':ident,'operation':'final','values':{'e1':10,'e2':3,'e3':3}}).json()
    assert result['grade']=='4' and result['passed'] is False
    result=learner.post('/api/knowledge/calculate',json={'policy_id':ident,'operation':'final','values':{'e1':7,'e2':7,'e3':3.5}}).json()
    assert result['passed'] is True
    result=learner.post('/api/knowledge/calculate',json={'policy_id':ident,'operation':'recovery','values':{'previous':2,'exam':6}}).json()
    assert result['raw']=='4' and result['grade']=='5'


def test_historical_english_needs_acknowledgement(app,learner):
    ident,_=policy(app,learner,'english',True)
    values={k:6 for k in ['listening','speaking','reading','writing','mediation','use_of_english','culture']};values['use_of_english_passed']=True
    assert learner.post('/api/knowledge/calculate',json={'policy_id':ident,'values':values}).status_code==409
    result=learner.post('/api/knowledge/calculate',json={'policy_id':ident,'values':values,'acknowledge_historical':True}).json()
    assert result['raw']=='6' and result['source']['verification']=='historical'
    values['writing']=0.5
    result=learner.post('/api/knowledge/calculate',json={'policy_id':ident,'values':values,'acknowledge_historical':True}).json()
    assert Decimal(result['grade'])<=4 and result['passed'] is False


def test_philosophy_formula_does_not_invent_missing_restrictions(app,learner):
    ident,_=policy(app,learner,'philosophy')
    result=learner.post('/api/knowledge/calculate',json={'policy_id':ident,'operation':'final','values':{'e1':5,'e2':6,'e3':7}}).json()
    assert result['raw']=='6.2' and result['status']=='missing_information' and result['passed'] is None


def test_target_grade_and_personal_tasks(app,learner,login):
    ident,_=policy(app,learner)
    result=learner.post('/api/knowledge/calculate',json={'policy_id':ident,'operation':'target','unknown_component':'exams','values':{'activities':10,'practical':10},'target':5}).json()
    assert abs(Decimal(result['required'])-Decimal('4.444444'))<Decimal('.00001')
    task=learner.post('/api/personal-tasks',json={'title':'Repaso privado','due_at':'2030-12-19T17:00:00+01:00'}).json()
    assert login().patch('/api/personal-tasks/'+task['id'],json={'completed':True}).status_code==404
    assert learner.patch('/api/personal-tasks/'+task['id'],json={'completed':True}).json()['completed']


def test_memory_cross_conversation_date_and_edit(learner,login):
    first=learner.post('/api/conversations',json={}).json()['id']
    send(learner,first,'Recuerda que el 19 de diciembre de 2030 tengo un examen')
    second=learner.post('/api/conversations',json={}).json()['id']
    answer=send(learner,second,'¿Qué tengo el 19 de diciembre de 2030?')['assistant_message']
    assert 'examen' in answer['content'] and any(t['name']=='search_memory' for t in answer['details']['tools'])
    memory=learner.get('/api/memory?q=examen').json()['memories'][0]
    body={'content':'Examen corregido','event_at':memory['event_at'],'expected_updated_at':memory['updated_at']}
    assert login().patch('/api/memory/'+memory['id'],json=body).status_code==404
    assert learner.patch('/api/memory/'+memory['id'],json=body).status_code==200
    assert learner.patch('/api/memory/'+memory['id'],json=body).status_code==409


def test_tomorrow_queries_schedule_calendar_and_memory(learner):
    convo=learner.post('/api/conversations',json={}).json()['id']
    response=send(learner,convo,'¿Qué tengo mañana?')['assistant_message']
    assert {'query_calendar','get_my_schedule','search_memory','query_assignments'}.issubset({t['name'] for t in response['details']['tools']})
    assert not response['details'].get('error')


def test_natural_personal_event_word_time_requires_review(learner):
    convo=learner.post('/api/conversations',json={}).json()['id']
    response=send(learner,convo,'Añade una sesión de estudio el jueves a las cinco')['assistant_message']
    assert response['details']['actions']
    action=response['details']['actions'][0]
    assert '17:00' in action['arguments']['starts_at']
    assert learner.post('/api/actions/'+action['id']+'/confirm').status_code==200


def test_study_drill_corrects_and_adapts_without_official_grades(learner,login):
    subject=next(s['id'] for s in learner.get('/api/learner').json()['subjects'] if s['name']=='Matemáticas I')
    result=learner.post('/api/study/sessions',json={'subject_id':subject,'topic':'Ecuaciones de primer grado'}).json()
    ex=result['exercises'][0];assert 'expected' not in ex
    assert login().post('/api/study/sessions/'+result['id']+'/answers',json={'exercise_id':ex['id'],'answer':'4'}).status_code==404
    # At level 1, index 0: 3x+2=11, so x=3.
    answer=learner.post('/api/study/sessions/'+result['id']+'/answers',json={'exercise_id':ex['id'],'answer':'3'}).json()
    assert answer['attempt']['correct'] is True and not answer['attempt']['official_grade']
    assert answer['session']['level']==2


def test_plan_uses_real_availability_and_confirmation(learner):
    assert learner.post('/api/study/plans',json={}).status_code==422
    for_day=[{'weekday':i,'starts':'17:00','ends':'19:00'} for i in range(7)]
    assert learner.put('/api/study/availability',json=for_day).status_code==200
    response=learner.post('/api/study/plans',json={'max_sessions':2,'start_day':'2030-12-18'}).json()
    assert response['status']=='pending_confirmation' and len(response['result']['sessions'])==2
    assert not learner.get('/api/events').json()
    assert learner.post('/api/actions/'+response['action']['id']+'/confirm').status_code==200
    assert len(learner.get('/api/events').json())==2


def test_docx_tracked_insertions_are_not_lost():
    from docx import Document
    from docx.oxml import OxmlElement
    from app.documents import extract
    document=Document();p=document.add_paragraph('Regla: ')
    ins=OxmlElement('w:ins');run=OxmlElement('w:r');text=OxmlElement('w:t');text.text='truncar los decimales';run.append(text);ins.append(run);p._p.append(ins)
    deleted=OxmlElement('w:del');r=OxmlElement('w:r');t=OxmlElement('w:t');t.text='regla obsoleta';r.append(t);deleted.append(r);p._p.append(deleted)
    stream=io.BytesIO();document.save(stream)
    content=' '.join(value for _,value in extract(stream.getvalue(),'.docx'))
    assert 'truncar los decimales' in content and 'regla obsoleta' not in content
