import json,sqlite3
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from fastapi.testclient import TestClient
from sqlalchemy import select
from app.db import utcnow,create_db
from app.models import User,ScheduledJob,JobExecution,Notification,Memory,SemanticVector,GradeScenario,MaterialDraft,AgentRun
from app.scheduler import execute_job,tick
from app.main import create_app
from app.backup import restore
from test_documents import upload
from test_memory_chat import send
from test_learning import learner,policy

def job_body(kind='upcoming_exams'):
    return {'title':'Revisión de prueba','kind':kind,'interval_hours':24,'next_run_at':(utcnow()+timedelta(minutes=1)).isoformat()}

def test_scheduler_claims_once_across_app_restart_and_honors_pause(app,login):
    c=login();job=c.post('/api/automations',json=job_body()).json();slot=job['next_run_at']
    first=c.post('/api/automations/'+job['id']+'/run',json={'scheduled_for':slot})
    assert first.status_code==200 and first.json()['status']=='completed'
    assert c.post('/api/automations/'+job['id']+'/run',json={'scheduled_for':slot}).json()['status']=='already_claimed'
    # A separate factory reopens the same SQLite file, as after a restart.
    engine,factory=create_db(app.state.settings.database_url)
    from datetime import datetime
    assert execute_job(factory,app.state.settings,job['id'],datetime.fromisoformat(slot))['status']=='already_claimed'
    engine.dispose()
    with app.state.session_factory() as db:
        assert len(list(db.scalars(select(JobExecution).where(JobExecution.job_id==job['id']))))==1
        assert len(list(db.scalars(select(Notification).where(Notification.dedup_key.like('automation:'+job['id']+'%')))))==1
    assert c.patch('/api/automations/'+job['id'],json={'enabled':False}).status_code==200
    current=c.get('/api/automations').json()[0]
    assert c.post('/api/automations/'+job['id']+'/run',json={'scheduled_for':current['next_run_at']}).json()['status']=='skipped'

def test_scheduled_jobs_acl_role_changed_and_notifications_off(app,login):
    student=login();admin=login('admin.demo');other=login('alumno2.demo')
    assert student.post('/api/automations',json=job_body('academic_report')).status_code==403
    job=student.post('/api/automations',json=job_body()).json()
    assert other.patch('/api/automations/'+job['id'],json={'enabled':False}).status_code==404
    assert admin.get('/api/automations').json()==[]
    student.put('/api/notification-preferences',json={'enabled':False})
    before=len(student.get('/api/notifications').json())
    assert student.post('/api/automations/'+job['id']+'/run',json={'scheduled_for':job['next_run_at']}).json()['status']=='completed'
    assert len(student.get('/api/notifications').json())==before
    assert student.delete('/api/automations/'+job['id']).json()['cancelled']
    assert student.patch('/api/automations/'+job['id'],json={'enabled':True}).status_code==409

def test_due_scheduler_module_control_and_stale_claims(app,login):
    c=login();admin=login('admin.demo');job=c.post('/api/automations',json=job_body()).json()
    with app.state.session_factory() as db:
        obj=db.get(ScheduledJob,job['id']);obj.next_run_at=utcnow()-timedelta(hours=1);db.commit()
    admin.patch('/api/admin/modules/scheduler',json={'enabled':False})
    assert tick(app.state.session_factory,app.state.settings)[0]['status']=='paused_by_policy'
    admin.patch('/api/admin/modules/scheduler',json={'enabled':True})
    assert tick(app.state.session_factory,app.state.settings)[0]['status']=='completed'
    assert tick(app.state.session_factory,app.state.settings)==[]

def test_material_review_share_confirmation_sources_acl_and_stale_version(app,login):
    teacher=login('profesor.demo');student=login();outside=login('alumno2.demo')
    meta=teacher.get('/api/academic').json();group=student.user['group_ids'][0];subject=next(t['subject_id'] for t in meta['teaching'] if t['group_id']==group)
    doc=upload(teacher,'source.txt',b'FuncionesDocumentoSeguroFicticio: una funcion relaciona cada entrada con una salida. Analiza dominio e imagen.',title='Funciones para repasar',access='group',group_id=group,subject_id=subject)
    assert doc.status_code==201,doc.text
    draft=teacher.post('/api/materials',json={'subject_id':subject,'title':'Guía de funciones','kind':'quiz','query':'FuncionesDocumentoSeguroFicticio'});assert draft.status_code==201,draft.text
    draft=draft.json();assert draft['state']=='draft' and draft['sources'][0]['document_id']==doc.json()['id']
    args={'material_id':draft['id'],'group_id':group,'version':draft['version']}
    assert teacher.post('/api/tools/call',json={'tool':'share_material','arguments':args}).status_code==409
    reviewed=teacher.patch('/api/materials/'+draft['id'],json={'content':draft['content'],'version':draft['version'],'reviewed':True}).json()
    args['version']=reviewed['version'];proposal=teacher.post('/api/tools/call',json={'tool':'share_material','arguments':args}).json()
    assert proposal['status']=='pending_confirmation'
    assert outside.patch('/api/materials/'+draft['id'],json={'content':draft['content'],'version':reviewed['version']}).status_code==404
    assert student.post('/api/actions/'+proposal['action']['id']+'/confirm').status_code==404
    approved=teacher.post('/api/actions/'+proposal['action']['id']+'/confirm');assert approved.status_code==200,approved.text
    doc_id=approved.json()['result']['document_id']
    assert student.get('/api/documents/'+doc_id+'/download').status_code==200
    assert outside.get('/api/documents/'+doc_id+'/download').status_code==404
    assert teacher.post('/api/actions/'+proposal['action']['id']+'/confirm').json()['result']==approved.json()['result']

def test_private_sources_never_leak_into_shared_material(app,login):
    c=login('profesor.demo');meta=c.get('/api/academic').json();subject=meta['teaching'][0]['subject_id'];group=meta['groups'][0]['id']
    upload(c,'private.txt',b'Contenido privado de geometria que no debe compartirse con el grupo.',title='Geometría personal',subject_id=subject)
    draft=c.post('/api/materials',json={'subject_id':subject,'title':'Geometría privada','query':'geometria'}).json()
    reviewed=c.patch('/api/materials/'+draft['id'],json={'content':draft['content'],'version':1,'reviewed':True}).json()
    assert c.post('/api/tools/call',json={'tool':'share_material','arguments':{'material_id':draft['id'],'group_id':group,'version':reviewed['version']}}).status_code==422

def test_private_criteria_cannot_be_laundered_through_group_fragments(app,login):
    from app.models import KnowledgeSource,EvaluationCriterion
    c=login('profesor.demo');meta=c.get('/api/academic').json();subject=meta['teaching'][0]['subject_id'];group=meta['groups'][0]['id']
    upload(c,'allowed.txt',b'ContenidoCompartidoUnico: relaciones entre conceptos y ejemplos de estudio.',title='Material permitido',access='group',group_id=group,subject_id=subject)
    with app.state.session_factory() as db:
        source=KnowledgeSource(owner_id=c.user['id'],subject_id=subject,title='Criterios privados',kind='manual',applicable_year='2026-2027');db.add(source);db.flush()
        db.add(EvaluationCriterion(owner_id=c.user['id'],subject_id=subject,source_id=source.id,code='PRIVADO',competence='Prueba',content='Contenido privado que no debe publicarse'));db.commit()
    draft=c.post('/api/materials',json={'subject_id':subject,'title':'Borrador mixto','query':'ContenidoCompartidoUnico'}).json()
    reviewed=c.patch('/api/materials/'+draft['id'],json={'content':draft['content'],'version':1,'reviewed':True}).json()
    response=c.post('/api/tools/call',json={'tool':'share_material','arguments':{'material_id':draft['id'],'group_id':group,'version':reviewed['version']}})
    assert response.status_code==422 and 'criterio' in response.text.lower()

def test_manual_backup_actual_restore_protected_paths_and_admin_acl(app,login,tmp_path):
    c=login();admin=login('admin.demo');marker='Privado en respaldo de prueba'
    c.post('/api/memory',json={'content':marker})
    assert c.post('/api/admin/operations/backups').status_code==403
    result=admin.post('/api/admin/operations/backups');assert result.status_code==201,result.text
    meta=result.json();assert meta['restored'] and meta['integrity']=='ok' and meta['migration']=='0008'
    archive=app.state.settings.data_dir/'protected-backups'/meta['name'];assert archive.stat().st_mode&0o777==0o600
    restored=restore(archive,tmp_path/'restored-admin-test')
    with sqlite3.connect(restored/'axon.sqlite3') as db:assert db.execute('SELECT count(*) FROM memories WHERE content=?',(marker,)).fetchone()[0]==1
    assert admin.get('/api/admin/operations/backups').json()['download_available'] is False
    assert c.get('/api/admin/operations/backups').status_code==403
    assert admin.get('/api/admin/operations/backups/'+meta['name']).status_code==404
    audit=admin.get('/api/admin/audit').text;assert marker not in audit and 'protected_backup_verified' in audit

def test_search_and_diagnostics_never_disclose_other_private_data(app,login):
    c=login();admin=login('admin.demo');other=login('alumno2.demo');marker='marcadorprivadoalfacentauro'
    c.post('/api/memory',json={'content':marker});convo=c.post('/api/conversations',json={}).json()['id'];send(c,convo,marker)
    for stranger in [admin,other]:assert not stranger.get('/api/search?q='+marker).json()['results']
    own=c.get('/api/search?q='+marker).json()['results'];assert {'memory','conversation'}<={r['kind'] for r in own}
    assert c.get('/api/admin/operations/diagnostics').status_code==403
    diagnostic=admin.get('/api/admin/operations/diagnostics');assert diagnostic.status_code==200,diagnostic.text
    assert marker not in diagnostic.text and convo not in diagnostic.text
    assert diagnostic.json()['database']['migration']=='0008'
    assert all(marker not in json.dumps(record) and convo not in json.dumps(record) for record in app.state.metrics)

def test_grade_scenarios_saved_only_explicitly_and_private(app,learner,login):
    ident,_=policy(app,learner);body={'policy_id':ident,'values':{'exams':6,'activities':8,'practical':10}}
    assert learner.post('/api/knowledge/calculate',json=body).status_code==200
    assert learner.get('/api/knowledge/scenarios').json()==[]
    result=learner.post('/api/knowledge/scenarios',json=body);assert result.status_code==201
    assert result.json()['raw']=='6.3' and result.json()['scenario_id']
    saved=learner.get('/api/knowledge/scenarios').json();assert len(saved)==1 and saved[0]['result']['official'] is False
    assert login('admin.demo').get('/api/knowledge/scenarios').json()==[]

def test_new_private_records_export_and_erase(app,learner,login):
    c=learner;ident=c.post('/api/conversations',json={}).json()['id'];send(c,ident,'Recuerda el marcador de borrado de prueba')
    c.post('/api/automations',json=job_body())
    export=c.get('/api/profile/export').json();assert export['agent_runs'] and export['memory_annotations'] and export['scheduled_jobs']
    assert c.request('DELETE','/api/profile/data',json={'password':'Synthetic-Password!2026','confirmation':'ELIMINAR MIS DATOS'}).status_code==200
    with app.state.session_factory() as db:
        for model in (AgentRun,ScheduledJob,SemanticVector,GradeScenario,MaterialDraft):assert not list(db.scalars(select(model).where(model.user_id==c.user['id'])))

def test_additive_migration_preserves_02_rows_and_rejects_unknown_revision(app,tmp_path):
    from alembic.config import Config
    from alembic import command
    from app.config import ROOT
    from app.models import Center,Conversation,Message,Memory
    path=tmp_path/'legacy.sqlite3';settings=replace(app.state.settings,database_url=f'sqlite:///{path}',data_dir=tmp_path/'legacy-data')
    config=Config(str(ROOT/'backend/alembic.ini'));config.attributes['database_url']=settings.database_url;command.upgrade(config,'0002')
    engine,factory=create_db(settings.database_url)
    with factory() as db:
        center=Center(name='Centro legado ficticio',town='Prueba');db.add(center);db.flush()
        user=User(center_id=center.id,username='legacy.example',display_name='Ficticio legado',password_hash='unchanged-hash',role='student',active=False);db.add(user);db.flush()
        conversation=Conversation(user_id=user.id,title='Conservar 0.2');db.add(conversation);db.flush()
        db.add(Message(conversation_id=conversation.id,role='user',content='Mensaje legado sin cambios'));db.add(Memory(user_id=user.id,content='Recuerdo legado sin cambios'));db.commit();uid=user.id
    engine.dispose();upgraded=create_app(settings,maintenance=False)
    with upgraded.state.session_factory() as db:
        assert db.get(User,uid).password_hash=='unchanged-hash' and not db.get(User,uid).active
        assert db.scalar(select(Memory).where(Memory.user_id==uid)).content=='Recuerdo legado sin cambios'
    upgraded.state.engine.dispose()
    with sqlite3.connect(path) as db:db.execute("UPDATE alembic_version SET version_num='future-unknown'")
    import pytest
    with pytest.raises(Exception):create_app(settings,maintenance=False)
