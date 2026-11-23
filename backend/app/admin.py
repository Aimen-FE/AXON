import json
import secrets
from fastapi import APIRouter,Depends,HTTPException,Request,Response
from sqlalchemy import select,delete,func,text
from .auth import current_user,get_db,public_user,ph,verify,COOKIE
from .models import (User,Center,Group,Course,Teaching,Enrollment,AuditLog,Conversation,Message,
    Memory,MemorySummary,Document,DocumentChunk,CalendarEvent,Submission,Session,Notification,ActionRequest,BathroomPass)
from .schemas import UserCreate,UserUpdate,TeachingInput,GroupCreate,CenterInput,DeleteDataInput,StructureInput,EnrollmentInput
from .policy import require_role,require_group,audit
from .serializers import record

router=APIRouter(tags=['Administración y privacidad'])


@router.get('/admin/users')
def users(user=Depends(current_user),db=Depends(get_db)):
    require_role(user,'admin')
    return [public_user(db,u)|{'active':u.active} for u in db.scalars(select(User).where(User.center_id==user.center_id).order_by(User.role,User.display_name))]


@router.post('/admin/users',status_code=201)
def create_user(body:UserCreate,request:Request,user=Depends(current_user),db=Depends(get_db)):
    require_role(user,'admin')
    if request.app.state.settings.remote_demo:raise HTTPException(409,'La demostración remota utiliza las cuentas ficticias preparadas y sus invitaciones individuales')
    if db.scalar(select(User.id).where(User.username==body.username)):
        raise HTTPException(409,'Este identificador no está disponible')
    if body.role!='student' and body.group_ids:
        raise HTTPException(422,'Los grupos de matrícula corresponden al alumnado; asigna docentes desde Asignaciones')
    for gid in set(body.group_ids):require_group(db,user,gid)
    if request.app.state.settings.full_demo:
        if body.role == 'admin':
            raise HTTPException(403,'La demostración utiliza una sola administración ficticia')
        obj=User(center_id=user.center_id,username='demo.'+secrets.token_hex(10)+'.'+body.username,
                 display_name=body.display_name,password_hash='',role=body.role,is_demo=True,
                 preferences={'demo_roster':True})
    else:
        obj=User(center_id=user.center_id,username=body.username,display_name=body.display_name,password_hash=ph.hash(body.password),role=body.role,is_demo=user.is_demo)
    db.add(obj)
    db.flush()
    for gid in set(body.group_ids):db.add(Enrollment(user_id=obj.id,group_id=gid))
    audit(db,user,'user_created',obj,{'role':obj.role})
    db.commit()
    return public_user(db,obj)|{'active':obj.active}


@router.patch('/admin/users/{user_id}')
def update_user(user_id:str,body:UserUpdate,request:Request,user=Depends(current_user),db=Depends(get_db)):
    require_role(user,'admin')
    if db.bind.dialect.name == 'sqlite':
        db.execute(text('BEGIN IMMEDIATE'))
        db.refresh(user)
        require_role(user,'admin')
        if not user.active:
            raise HTTPException(403,'La cuenta administrativa ya no está activa')
    obj=db.get(User,user_id)
    if not obj or obj.center_id!=user.center_id:raise HTTPException(404,'Cuenta no disponible')
    if not obj.password_hash and body.active and not request.app.state.settings.remote_demo:
        raise HTTPException(409,'La cuenta debe configurar primero su contraseña')
    next_active = body.active if body.active is not None else obj.active
    next_role = body.role or obj.role
    if obj.id==user.id and (not next_active or next_role != obj.role):
        raise HTTPException(422,'Otro administrador debe gestionar el estado o el rol de tu cuenta')
    if request.app.state.settings.remote_demo and body.active:
        from .models import RemoteInvitation
        invite=db.scalar(select(RemoteInvitation).where(RemoteInvitation.user_id==obj.id,RemoteInvitation.consumed.is_(True),RemoteInvitation.revoked.is_(False)))
        if not invite:raise HTTPException(409,'Esta cuenta necesita una invitación individual válida')
    if next_role != obj.role:
        if request.app.state.settings.remote_demo:
            raise HTTPException(409,'Las cuentas invitadas mantienen su rol inicial')
        audit(db,user,'user_role_changed',obj,{'previous_role':obj.role,'role':next_role})
        obj.role=next_role
        db.execute(delete(Session).where(Session.user_id==obj.id))
    if next_active != obj.active:
        obj.active=next_active
        if not next_active:db.execute(delete(Session).where(Session.user_id==obj.id))
        audit(db,user,'user_status_changed',obj,{'active':next_active})
    db.commit()
    return public_user(db,obj)|{'active':obj.active}


@router.post('/admin/groups',status_code=201)
def create_group(body:GroupCreate,user=Depends(current_user),db=Depends(get_db)):
    require_role(user,'admin')
    course=db.get(Course,body.course_id)
    if not course or course.center_id!=user.center_id:raise HTTPException(404,'Curso no disponible')
    if db.scalar(select(Group.id).where(Group.center_id==user.center_id,Group.name==body.name)):
        raise HTTPException(409,'El grupo ya existe')
    obj=Group(center_id=user.center_id,course_id=course.id,name=body.name)
    db.add(obj)
    db.flush()
    audit(db,user,'group_created',obj)
    db.commit()
    return record(obj)


@router.post('/admin/teaching',status_code=201)
def teaching(body:TeachingInput,user=Depends(current_user),db=Depends(get_db)):
    require_role(user,'admin')
    require_group(db,user,body.group_id,body.subject_id,write=True)
    teacher=db.get(User,body.teacher_id)
    if not teacher or teacher.center_id!=user.center_id or teacher.role!='teacher' or not teacher.active:
        raise HTTPException(422,'Docente no disponible')
    if db.scalar(select(Teaching.id).where(Teaching.teacher_id==teacher.id,Teaching.group_id==body.group_id,Teaching.subject_id==body.subject_id)):
        raise HTTPException(409,'Esta asignación ya existe')
    obj=Teaching(**body.model_dump())
    db.add(obj)
    db.flush()
    audit(db,user,'teaching_created',obj)
    db.commit()
    return record(obj)


@router.patch('/admin/center')
def center(body:CenterInput,user=Depends(current_user),db=Depends(get_db)):
    require_role(user,'admin')
    obj=db.get(Center,user.center_id)
    obj.name,obj.town=body.name,body.town
    obj.settings=dict(obj.settings,bathroom_retention_days=body.bathroom_retention_days,automation_enabled=body.automation_enabled)
    audit(db,user,'center_configured',obj,{'retention_days':body.bathroom_retention_days,'automation_enabled':body.automation_enabled})
    db.commit()
    return record(obj)


@router.get('/admin/audit')
def logs(user=Depends(current_user),db=Depends(get_db)):
    require_role(user,'admin')
    return [record(x) for x in db.scalars(select(AuditLog).where(AuditLog.center_id==user.center_id).order_by(AuditLog.created_at.desc()).limit(200))]


@router.get('/profile/export')
def export(user=Depends(current_user),db=Depends(get_db)):
    convos=list(db.scalars(select(Conversation).where(Conversation.user_id==user.id)))
    docs=list(db.scalars(select(Document).where(Document.owner_id==user.id)))
    payload={'format':'AXON personal export v1','user':public_user(db,user),
        'conversations':[dict(record(c),messages=[record(m) for m in db.scalars(select(Message).where(Message.conversation_id==c.id).order_by(Message.created_at))]) for c in convos],
        'memories':[record(x) for x in db.scalars(select(Memory).where(Memory.user_id==user.id))],
        'summaries':[record(x) for x in db.scalars(select(MemorySummary).where(MemorySummary.conversation_id.in_([c.id for c in convos])))],
        'documents':[dict(record(d,('storage_key',)),chunks=[record(c) for c in db.scalars(select(DocumentChunk).where(DocumentChunk.document_id==d.id))]) for d in docs],
        'personal_events':[record(x) for x in db.scalars(select(CalendarEvent).where(CalendarEvent.owner_id==user.id,CalendarEvent.visibility=='personal'))],
        'submissions':[record(x) for x in db.scalars(select(Submission).where(Submission.student_id==user.id))],
        'notifications':[record(x) for x in db.scalars(select(Notification).where(Notification.user_id==user.id))]}
    from .knowledge import knowledge_data,profile_for
    from .models import LearnerSubject,LearningProgress,StudySession,StudyPlan,PersonalTask,IntegrationConnection
    payload['format']='AXON personal export v2'
    payload['academic_knowledge']=knowledge_data(db,user)
    profile=profile_for(db,user);payload['learner_profile']=record(profile) if profile else None
    for model in (LearnerSubject,LearningProgress,StudySession,StudyPlan,PersonalTask,IntegrationConnection):
        payload[model.__tablename__]=[record(x,('encrypted_payload',)) for x in db.scalars(select(model).where(model.user_id==user.id))]
    from .models import AgentRun,AgentStep,MemoryAnnotation,MemoryRelation,SemanticVector,ScheduledJob,JobExecution,GradeScenario,MaterialDraft,IntegrationSync
    for model in (AgentRun,MemoryAnnotation,MemoryRelation,SemanticVector,ScheduledJob,GradeScenario,MaterialDraft,IntegrationSync):
        payload[model.__tablename__]=[record(x) for x in db.scalars(select(model).where(model.user_id==user.id))]
    payload['agent_steps']=[record(x) for x in db.scalars(select(AgentStep).join(AgentRun).where(AgentRun.user_id==user.id))]
    payload['job_executions']=[record(x) for x in db.scalars(select(JobExecution).join(ScheduledJob).where(ScheduledJob.user_id==user.id))]
    payload['format']='AXON personal export v3'
    return Response(json.dumps(payload,ensure_ascii=False,indent=2),media_type='application/json',headers={'Content-Disposition':'attachment; filename="axon-mis-datos.json"','Cache-Control':'no-store'})


@router.delete('/profile/data')
def erase(body:DeleteDataInput,request:Request,response:Response,user=Depends(current_user),db=Depends(get_db)):
    from .operations import storage_lock
    with storage_lock(request.app.state.settings):return erase_data(body,request,response,user,db)

def erase_data(body,request,response,user,db):
    if not verify(body.password,user.password_hash):raise HTTPException(403,'Contraseña incorrecta')
    if user.role=='admin' and db.scalar(select(func.count()).select_from(User).where(User.center_id==user.center_id,User.role=='admin',User.active.is_(True)))<=1:
        raise HTTPException(409,'Crea otro administrador activo antes de eliminar esta cuenta')
    from .models import (AccountSetup,LearnerProfile,LearnerSubject,KnowledgeSource,LearningProgress,StudySession,StudyPlan,PersonalTask,IntegrationConnection,OAuthAttempt,AgentRun,MemoryAnnotation,MemoryRelation,SemanticVector,ScheduledJob,GradeScenario,MaterialDraft,IntegrationSync)
    for model in (AgentRun,MemoryRelation,MemoryAnnotation,SemanticVector,ScheduledJob,GradeScenario,MaterialDraft,IntegrationSync):db.execute(delete(model).where(model.user_id==user.id))
    # Delete private relations even when a source has no original document. Never export tokens.
    for model,condition in [(AccountSetup,AccountSetup.user_id==user.id),(OAuthAttempt,OAuthAttempt.user_id==user.id),(IntegrationConnection,IntegrationConnection.user_id==user.id),(StudySession,StudySession.user_id==user.id),(StudyPlan,StudyPlan.user_id==user.id),(PersonalTask,PersonalTask.user_id==user.id),(LearningProgress,LearningProgress.user_id==user.id),(LearnerSubject,LearnerSubject.user_id==user.id),(LearnerProfile,LearnerProfile.user_id==user.id),(KnowledgeSource,KnowledgeSource.owner_id==user.id)]:db.execute(delete(model).where(condition))
    from .class_models import ClassEvent, ClassFile
    shared_files = select(ClassFile.document_id).where(ClassFile.submission_id.is_(None))
    private_docs=list(db.scalars(select(Document).where(Document.owner_id==user.id,Document.access=='personal',
                                                        Document.id.not_in(shared_files))))
    keys=[d.storage_key for d in private_docs]
    for d in private_docs:db.delete(d)
    for model,condition in [
        (Conversation,Conversation.user_id==user.id),(Memory,Memory.user_id==user.id),
        (CalendarEvent,(CalendarEvent.owner_id==user.id)&(CalendarEvent.visibility=='personal')&
         CalendarEvent.id.not_in(select(ClassEvent.event_id))),
        (Submission,Submission.student_id==user.id),(Session,Session.user_id==user.id),
        (Notification,Notification.user_id==user.id),(ActionRequest,ActionRequest.user_id==user.id),
        (BathroomPass,BathroomPass.student_id==user.id),(Enrollment,Enrollment.user_id==user.id)]:
        db.execute(delete(model).where(condition))
    audit(db,user,'personal_data_erased',user,{'institutional_records_retained':True})
    user.username='deleted-'+user.id
    user.display_name='Cuenta eliminada'
    user.password_hash=ph.hash(secrets.token_urlsafe(40))
    user.preferences={}
    user.active=False
    db.commit()
    for key in keys:(request.app.state.settings.data_dir/'uploads'/key).unlink(missing_ok=True)
    response.delete_cookie(COOKIE,path='/')
    return {'ok':True,'message':'Cuenta desactivada y datos privados eliminados. Los registros institucionales y de auditoría conservan un identificador interno.'}


@router.post('/admin/structure',status_code=201)
def structure(body:StructureInput,user=Depends(current_user),db=Depends(get_db)):
    from .models import AcademicYear,Subject,Classroom
    require_role(user,'admin')
    cls={'year':AcademicYear,'course':Course,'subject':Subject,'classroom':Classroom}[body.kind]
    if db.scalar(select(cls.id).where(cls.center_id==user.center_id,cls.name==body.name)):
        raise HTTPException(409,'Ya existe un registro con ese nombre')
    values={'center_id':user.center_id,'name':body.name}
    if body.kind=='course':
        year=db.get(AcademicYear,body.year_id) if body.year_id else None
        if not year or year.center_id!=user.center_id:raise HTTPException(422,'Selecciona un curso académico válido')
        values.update(year_id=year.id,stage=body.stage)
    elif body.kind=='subject':values['color']=body.color
    obj=cls(**values)
    db.add(obj);db.flush()
    audit(db,user,'structure_created',obj,{'kind':body.kind})
    db.commit()
    return record(obj)


@router.post('/admin/enrollments',status_code=201)
def enrollment(body:EnrollmentInput,user=Depends(current_user),db=Depends(get_db)):
    require_role(user,'admin')
    require_group(db,user,body.group_id)
    student=db.get(User,body.student_id)
    if not student or student.center_id!=user.center_id or student.role!='student' or not student.active:
        raise HTTPException(422,'Alumno no disponible')
    if db.scalar(select(Enrollment.id).where(Enrollment.user_id==student.id,Enrollment.group_id==body.group_id)):
        raise HTTPException(409,'La matrícula ya existe')
    obj=Enrollment(user_id=student.id,group_id=body.group_id)
    db.add(obj);db.flush();audit(db,user,'student_enrolled',obj);db.commit()
    return record(obj)
