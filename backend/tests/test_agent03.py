import asyncio
from datetime import timedelta
import pytest
from fastapi import HTTPException
from sqlalchemy import select
from app.models import AgentRun,AgentStep,User,Conversation,Message,Memory,MemoryAnnotation,CalendarEvent,Center,CenterModule
from app.db import utcnow
from app import orchestrator
from test_memory_chat import send

def convo(client):return client.post('/api/conversations',json={}).json()['id']

def test_compound_real_queries_plan_confirmation_and_persistence(app,login):
    c=login();ident=convo(c)
    assert c.put('/api/study/availability',json=[{'weekday':i,'starts':'17:00','ends':'19:00'} for i in range(5)]).status_code==200
    answer=send(c,ident,'Consulta mis exámenes, revisa las tareas pendientes, busca información para prepararme y organiza mi semana')
    details=answer['assistant_message']['details'];assert details['run_id'] and len(details['tools'])==6
    run=c.get('/api/agent/runs/'+details['run_id']).json()
    assert run['status']=='awaiting_confirmation'
    assert [s['tool'] for s in run['steps']]==['query_exams','get_pending','get_my_schedule','get_study_context','search_documents','create_study_plan']
    assert all(s['verified'] for s in run['steps'][:-1])
    action=details['actions'][0]
    approved=c.post('/api/actions/'+action['id']+'/confirm');assert approved.status_code==200,approved.text
    assert c.post('/api/actions/'+action['id']+'/confirm').json()['result']==approved.json()['result']
    updated=c.get('/api/agent/runs/'+run['id']).json();assert updated['status']=='completed'
    assert updated['steps'][-1]['verified']
    history=c.get('/api/conversations/'+ident).json();assert len(history['messages'])==2

def test_run_history_private_even_to_admin(app,login):
    c=login();result=send(c,convo(c),'¿Qué exámenes tengo?');ident=result['assistant_message']['details']['run_id']
    for stranger in [login('alumno2.demo'),login('admin.demo')]:
        assert stranger.get('/api/agent/runs/'+ident).status_code==404
        assert stranger.post('/api/agent/runs/'+ident+'/cancel').status_code==404
        assert all(run['id']!=ident for run in stranger.get('/api/agent/runs').json())

def execute_plan(app,c,calls):
    with app.state.session_factory() as db:
        user=db.get(User,c.user['id']);conversation=Conversation(user_id=user.id,title='Plan de prueba');db.add(conversation);db.flush()
        message=Message(conversation_id=conversation.id,role='user',content='Prueba estructurada',client_id='agent-test');db.add(message);db.commit()
        return asyncio.run(orchestrator.execute(app,user,conversation.id,message.id,{'calls':calls}))

def test_transient_read_retry_partial_failures_and_no_write_retry(app,login,monkeypatch):
    c=login();original=orchestrator.perform;attempts={}
    def flaky(factory,uid,name,args,*rest):
        attempts[name]=attempts.get(name,0)+1
        if name=='query_exams' and attempts[name]==1:raise HTTPException(503,'Conexión temporal')
        if name=='get_pending':raise HTTPException(422,'Datos incompletos')
        if name=='save_memory':raise HTTPException(503,'No se sabe si llegó a guardarse')
        return original(factory,uid,name,args,*rest)
    monkeypatch.setattr(orchestrator,'perform',flaky)
    results,run,failures=execute_plan(app,c,[('query_exams',{}),('get_pending',{}),('save_memory',{'content':'No duplicar'}),('query_calendar',{})])
    assert run['status']=='partial' and len(failures)==2
    assert attempts=={'query_exams':2,'get_pending':1,'save_memory':1,'query_calendar':1}
    assert run['steps'][0]['status']=='completed' and run['steps'][0]['attempts']==2
    assert len(results)==2

def test_invalid_model_tool_arguments_do_not_rollback_prior_steps(app,login):
    c=login();results,run,failures=execute_plan(app,c,[('save_memory',{'content':'Recuerdo que debe persistir'}),('query_exams',{'arbitrary':'extra'})])
    assert run['status']=='partial' and run['steps'][1]['error_code']=='422'
    assert any(m['content']=='Recuerdo que debe persistir' for m in c.get('/api/memory').json()['memories'])
    with app.state.session_factory() as db:
        annotation=db.scalar(select(MemoryAnnotation).where(MemoryAnnotation.user_id==c.user['id']))
        assert annotation.source_message_id and annotation.state=='provisional'

def test_cancellation_between_steps_never_undoes_completed_step(app,login,monkeypatch):
    c=login();original=orchestrator.perform
    def cancel_after(*args):
        result=original(*args)
        with app.state.session_factory() as db:
            run=db.scalar(select(AgentRun).where(AgentRun.user_id==c.user['id']));run.cancel_requested=True;db.commit()
        return result
    monkeypatch.setattr(orchestrator,'perform',cancel_after)
    results,run,_=execute_plan(app,c,[('query_exams',{}),('save_memory',{'content':'No debería guardarse'})])
    assert run['status']=='cancelled' and run['steps'][0]['status']=='completed' and run['steps'][1]['status']=='cancelled'
    assert c.get('/api/memory?q=debería').json()['memories']==[]

def test_step_limit_and_recovery_of_stale_run(app,login):
    c=login()
    with pytest.raises(HTTPException) as error:execute_plan(app,c,[('query_exams',{})]*9)
    assert error.value.status_code==422
    execute_plan(app,c,[('query_exams',{})])
    with app.state.session_factory() as db:
        run=db.scalar(select(AgentRun).where(AgentRun.user_id==c.user['id']));run.status='running';run.deadline_at=utcnow()-timedelta(seconds=1)
        step=db.scalar(select(AgentStep).where(AgentStep.run_id==run.id));step.status='running';db.commit();ident=run.id
    recovered=c.get('/api/agent/runs/'+ident).json();assert recovered['status']=='partial'
    assert recovered['steps'][0]['status']=='interrupted'

def test_modules_enforced_on_direct_api_tools_and_confirmations(app,login):
    admin=login('admin.demo');student=login()
    assert student.patch('/api/admin/modules/math',json={'enabled':False}).status_code==403
    assert admin.patch('/api/admin/modules/math',json={'enabled':False}).status_code==200
    assert student.post('/api/math',json={'expression':'2+2'}).status_code==409
    assert student.post('/api/tools/call',json={'tool':'calculate_math','arguments':{'expression':'2+2'}}).status_code==409
    assert student.get('/api/profile/export').status_code==200
    assert any(m['key']=='math' and not m['enabled'] for m in student.get('/api/modules').json())
    with app.state.session_factory() as db:
        other=Center(name='Segundo centro',town='Prueba');db.add(other);db.flush()
        outside=User(center_id=other.id,username='outside.agent',display_name='Ficticio',password_hash='',role='admin');db.add(outside);db.flush()
        from app.extensions import enabled
        assert enabled(db,outside,'math')

def test_compound_never_uses_private_exam_as_external_query(app,login):
    c=login();send(c,convo(c),'Consulta mis exámenes, busca información y organiza mi semana')
    run=c.get('/api/agent/runs').json()[0]
    assert all(s['tool'] not in ('search_public','research_sources') for s in run['steps'])

def test_agent_math_chat_deterministic(login):
    c=login();result=send(c,convo(c),'Resuelve x^2-4')
    assert result['assistant_message']['details']['tools']==[{'name':'calculate_math','status':'completed'}]
    assert '-2' in result['assistant_message']['content'] and '2' in result['assistant_message']['content']
