from collections import defaultdict
from datetime import datetime
from fastapi import APIRouter,Depends,HTTPException,Request,Response
from sqlalchemy import select,update
from .auth import get_db,current_user,digest,ph,public_user,COOKIE
from .db import utcnow
from .serializers import record
from .models import (User,Session,Subject,Document,KnowledgeSource,LearnerProfile,LearnerSubject,
    AcademicTeacher,PersonalScheduleSlot,CourseUnit,EvaluationCriterion,AssessmentPolicy,
    LearningProgress,AccountSetup,PersonalTask,AcademicYear,Group)
from .learning_schemas import (SetupInspect,SetupFinish,LearnerUpdate,AcademicImport,ProgressInput,
    CalculatorInput,PrivateSlotUpdate,PersonalTaskInput,PersonalTaskUpdate,ManualKnowledge)
from .academic_import import create_source_from_document,normalize
from .grades import calculate
from .memory import MADRID,day_bounds

router=APIRouter(tags=['Perfil privado y conocimiento académico'])


def profile_for(db,user):
    return db.scalar(select(LearnerProfile).where(LearnerProfile.user_id==user.id))

def source_for(db,user,ident):
    source=db.scalar(select(KnowledgeSource).where(KnowledgeSource.id==ident,KnowledgeSource.owner_id==user.id))
    if not source:raise HTTPException(404,'Fuente no disponible')
    return source

def subject_for(db,user,ident,selected=False):
    subject=db.get(Subject,ident)
    if not subject or subject.center_id!=user.center_id:raise HTTPException(404,'Asignatura no disponible')
    if not profile_for(db,user) and user.role!='admin':
        from .policy import group_ids
        from .models import Teaching
        if not db.scalar(select(Teaching.id).where(Teaching.subject_id==ident,Teaching.group_id.in_(group_ids(db,user)))):raise HTTPException(404,'Asignatura fuera de tu ámbito académico')
    if selected and not db.scalar(select(LearnerSubject.id).where(LearnerSubject.user_id==user.id,LearnerSubject.subject_id==ident,LearnerSubject.active.is_(True))):
        raise HTTPException(404,'La materia no está seleccionada en tu matrícula personal')
    return subject


def personal_schedule(db,user,day=None,subject_id=None):
    calendar_note=''
    if day:
        profile=profile_for(db,user);calendar=profile.preferences.get('school_calendar',{}) if profile else {}
        if calendar:
            outside=day<calendar.get('starts','0000') or day>calendar.get('ends','9999')
            reason=calendar.get('non_school_days',{}).get(day)
            for interval in calendar.get('breaks',[]):
                if interval['starts']<=day<=interval['ends']:reason=interval['title']
            if outside or reason:return {'lessons':[],'pending_blocks':[],'group_options':[],'calendar_note':('Fecha fuera del período lectivo documentado' if outside else 'Día no lectivo: '+reason)+'. Fuente: '+calendar.get('source_title','calendario aportado'),'note':'Calendario escolar contrastado; pueden existir cambios posteriores del centro.'}
            calendar_note='Se aplica el calendario escolar contrastado; las modificaciones particulares del centro requieren confirmación.'
    selected=set(db.scalars(select(LearnerSubject.subject_id).where(LearnerSubject.user_id==user.id,LearnerSubject.active.is_(True))))
    stmt=select(PersonalScheduleSlot).where(PersonalScheduleSlot.owner_id==user.id)
    if day:
        day_bounds(day);weekday=datetime.fromisoformat(day).weekday();stmt=stmt.where(PersonalScheduleSlot.weekday==weekday)
    rows=list(db.scalars(stmt.order_by(PersonalScheduleSlot.weekday,PersonalScheduleSlot.starts,PersonalScheduleSlot.raw_code)))
    subjects={s.id:s.name for s in db.scalars(select(Subject).where(Subject.center_id==user.center_id))}
    sources={s.id:s for s in db.scalars(select(KnowledgeSource).where(KnowledgeSource.owner_id==user.id))}
    lessons=[];alternatives=defaultdict(list)
    for slot in rows:
        item=record(slot)|{'subject_name':subjects.get(slot.subject_id,'Recreo'),'selected':slot.subject_id in selected or slot.is_break,
             'source_title':sources[slot.source_id].title,'verification':sources[slot.source_id].verification}
        if item['selected'] and (not subject_id or slot.subject_id==subject_id or slot.is_break):lessons.append(item)
        if not slot.is_break:alternatives[(slot.weekday,slot.starts,slot.ends)].append(item)
    pending=[{'weekday':key[0],'starts':key[1],'ends':key[2],'options':items} for key,items in alternatives.items() if not any(x['selected'] for x in items)]
    return {'lessons':lessons,'pending_blocks':pending,'group_options':[r for items in alternatives.values() for r in items],
            'calendar_note':calendar_note,'note':'Horario aportado por el titular; las alternativas no seleccionadas no se matriculan automáticamente.'}


def knowledge_data(db,user,subject_id=None):
    if subject_id:subject_for(db,user,subject_id)
    sources=list(db.scalars(select(KnowledgeSource).where(KnowledgeSource.owner_id==user.id)))
    if subject_id:sources=[s for s in sources if s.subject_id==subject_id]
    ids=[s.id for s in sources]
    import re
    units=[record(u) for u in db.scalars(select(CourseUnit).where(CourseUnit.owner_id==user.id,CourseUnit.source_id.in_(ids)))]
    names={s.id:s.name for s in db.scalars(select(Subject).where(Subject.center_id==user.center_id))}
    units.sort(key=lambda u:(names.get(u['subject_id'],''),u['term'] or 0,int(re.search(r'\d+',u['code'])[0]) if re.search(r'\d+',u['code']) else 0,u['code']))
    return {'sources':[record(s) for s in sources],
        'policies':[record(p) for p in db.scalars(select(AssessmentPolicy).where(AssessmentPolicy.owner_id==user.id,AssessmentPolicy.source_id.in_(ids)))],
        'units':units,
        'criteria':[record(c) for c in db.scalars(select(EvaluationCriterion).where(EvaluationCriterion.owner_id==user.id,EvaluationCriterion.source_id.in_(ids)).order_by(EvaluationCriterion.code))],
        'teachers':[record(t) for t in db.scalars(select(AcademicTeacher).where(AcademicTeacher.owner_id==user.id,AcademicTeacher.source_id.in_(ids)))]}


@router.post('/onboarding/inspect')
def inspect_setup(body:SetupInspect,db=Depends(get_db)):
    setup=db.scalar(select(AccountSetup).where(AccountSetup.token_hash==digest(body.token),AccountSetup.used.is_(False),AccountSetup.expires_at>utcnow()))
    if not setup:raise HTTPException(404,'El enlace privado ha caducado o ya se ha utilizado')
    user=db.get(User,setup.user_id)
    return {'display_name':user.display_name,'username':user.username,'role':user.role,'minimum_password_length':12}


@router.post('/onboarding/finish')
def finish_setup(body:SetupFinish,request:Request,response:Response,db=Depends(get_db)):
    import secrets
    from datetime import timedelta
    setup=db.scalar(select(AccountSetup).where(AccountSetup.token_hash==digest(body.token),AccountSetup.used.is_(False),AccountSetup.expires_at>utcnow()))
    if not setup:raise HTTPException(404,'El enlace privado ha caducado o ya se ha utilizado')
    changed=db.execute(update(AccountSetup).where(AccountSetup.id==setup.id,AccountSetup.used.is_(False)).values(used=True)).rowcount
    if not changed:raise HTTPException(409,'El enlace ya ha sido utilizado')
    user=db.get(User,setup.user_id)
    if user.active:raise HTTPException(409,'La cuenta ya está configurada')
    user.password_hash=ph.hash(body.password);user.active=True
    token=secrets.token_urlsafe(32);csrf=secrets.token_urlsafe(32)
    db.add(Session(user_id=user.id,token_hash=digest(token),csrf_token=csrf,expires_at=utcnow()+timedelta(hours=12)))
    db.commit()
    response.set_cookie(COOKIE,token,httponly=True,secure=request.app.state.settings.cookie_secure,samesite='strict',max_age=43200,path='/')
    return {'user':public_user(db,user),'csrf_token':csrf}


@router.get('/learner')
def learner(user=Depends(current_user),db=Depends(get_db)):
    profile=profile_for(db,user)
    selected=list(db.scalars(select(LearnerSubject.subject_id).where(LearnerSubject.user_id==user.id,LearnerSubject.active.is_(True))))
    return {'profile':(record(profile)|{'academic_year':db.get(AcademicYear,profile.year_id).name,'group_label':db.get(Group,profile.group_id).name}) if profile else None,'subject_ids':selected,
            'subjects':[record(s) for s in db.scalars(select(Subject).where(Subject.center_id==user.center_id))] if profile else [],
            'teachers':[record(t) for t in db.scalars(select(AcademicTeacher).where(AcademicTeacher.owner_id==user.id))]}


@router.put('/learner')
def update_learner(body:LearnerUpdate,user=Depends(current_user),db=Depends(get_db)):
    profile=profile_for(db,user)
    if not profile:raise HTTPException(404,'No hay un perfil académico privado configurado')
    if any(k in body.preferences for k in ('schedule_code_map','school_calendar')):raise HTTPException(422,'El mapa de códigos se cambia mediante la revisión de importación')
    for ident in body.subject_ids:subject_for(db,user,ident)
    available=body.availability
    for i,a in enumerate(available):
        if any(a.weekday==b.weekday and a.starts<b.ends and b.starts<a.ends for b in available[:i]):raise HTTPException(422,'Las franjas de disponibilidad se solapan')
    slots=list(db.scalars(select(PersonalScheduleSlot).where(PersonalScheduleSlot.owner_id==user.id,PersonalScheduleSlot.subject_id.in_(body.subject_ids))))
    for i,a in enumerate(slots):
        if any(a.weekday==b.weekday and a.starts<b.ends and b.starts<a.ends and a.subject_id!=b.subject_id for b in slots[:i]):raise HTTPException(409,'Has seleccionado alternativas que coinciden en el horario. Revisa la elección de materias')
    profile.preferences={**profile.preferences,**body.preferences};profile.availability=[a.model_dump() for a in available]
    old={r.subject_id:r for r in db.scalars(select(LearnerSubject).where(LearnerSubject.user_id==user.id))}
    for ident,row in old.items():row.active=ident in body.subject_ids
    for ident in set(body.subject_ids)-set(old):db.add(LearnerSubject(user_id=user.id,subject_id=ident,active=True))
    db.commit();return {'ok':True}


@router.get('/learner/schedule')
def schedule(day:str|None=None,subject_id:str|None=None,user=Depends(current_user),db=Depends(get_db)):
    if subject_id:subject_for(db,user,subject_id)
    return personal_schedule(db,user,day,subject_id)


@router.patch('/learner/schedule/{slot_id}')
def edit_slot(slot_id:str,body:PrivateSlotUpdate,user=Depends(current_user),db=Depends(get_db)):
    row=db.scalar(select(PersonalScheduleSlot).where(PersonalScheduleSlot.id==slot_id,PersonalScheduleSlot.owner_id==user.id))
    if not row:raise HTTPException(404,'Sesión privada no disponible')
    selected=set(db.scalars(select(LearnerSubject.subject_id).where(LearnerSubject.user_id==user.id,LearnerSubject.active.is_(True))))
    if row.subject_id in selected or row.is_break:
        overlap=db.scalar(select(PersonalScheduleSlot.id).where(PersonalScheduleSlot.owner_id==user.id,PersonalScheduleSlot.id!=row.id,PersonalScheduleSlot.weekday==row.weekday,PersonalScheduleSlot.starts<body.ends,PersonalScheduleSlot.ends>body.starts,PersonalScheduleSlot.subject_id.in_(selected)))
        if overlap:raise HTTPException(409,'La franja se solapa con otra materia seleccionada')
    for k,v in body.model_dump().items():setattr(row,k,v)
    row.overridden=True;db.commit()
    return record(row)


@router.get('/knowledge')
def knowledge(subject_id:str|None=None,user=Depends(current_user),db=Depends(get_db)):
    return knowledge_data(db,user,subject_id)


@router.post('/knowledge/import')
def import_document(body:AcademicImport,request:Request,user=Depends(current_user),db=Depends(get_db)):
    document=db.scalar(select(Document).where(Document.id==body.document_id,Document.owner_id==user.id))
    if not document:raise HTTPException(404,'Documento propio no disponible')
    existing=db.scalar(select(KnowledgeSource).where(KnowledgeSource.owner_id==user.id,KnowledgeSource.document_id==document.id))
    if existing and (existing.kind!=body.kind or existing.subject_id!=body.subject_id or existing.applicable_year!=body.applicable_year):
        raise HTTPException(409,'Este documento ya tiene una importación diferente. Conserva su fuente o importa una nueva versión')
    if body.kind in ('physics','technology','english') and not body.subject_id:raise HTTPException(422,'Selecciona la asignatura antes de importar sus criterios')
    if body.subject_id:
        subject_for(db,user,body.subject_id);document.subject_id=body.subject_id
    source,result=create_source_from_document(db,user,document,body.kind,body.applicable_year,body.academic_year,request.app.state.settings)
    db.commit();return {'source':record(source),'result':result}


@router.get('/knowledge/progress')
def progress(user=Depends(current_user),db=Depends(get_db)):
    return [record(p) for p in db.scalars(select(LearningProgress).where(LearningProgress.user_id==user.id))]


@router.put('/knowledge/progress/{unit_id}')
def update_progress(unit_id:str,body:ProgressInput,user=Depends(current_user),db=Depends(get_db)):
    unit=db.scalar(select(CourseUnit).where(CourseUnit.id==unit_id,CourseUnit.owner_id==user.id))
    if not unit:raise HTTPException(404,'Unidad no disponible')
    p=db.scalar(select(LearningProgress).where(LearningProgress.unit_id==unit_id,LearningProgress.user_id==user.id))
    if not p:p=LearningProgress(user_id=user.id,unit_id=unit.id);db.add(p)
    for k,v in body.model_dump().items():setattr(p,k,v)
    db.commit();return record(p)


@router.post('/knowledge/calculate')
def grade(body:CalculatorInput,user=Depends(current_user),db=Depends(get_db)):
    return calculate(db,user,body)

@router.post('/knowledge/scenarios',status_code=201)
def save_scenario(body:CalculatorInput,user=Depends(current_user),db=Depends(get_db)):
    from .models import GradeScenario,AssessmentPolicy
    result=calculate(db,user,body)
    policy=db.scalar(select(AssessmentPolicy).where(AssessmentPolicy.id==body.policy_id,AssessmentPolicy.owner_id==user.id))
    if not policy:raise HTTPException(404,'Regla no disponible')
    obj=GradeScenario(user_id=user.id,subject_id=policy.subject_id,policy_id=policy.id,input=body.model_dump(mode='json'),result=result)
    db.add(obj);db.commit();return dict(result,scenario_id=obj.id,saved_at=obj.created_at.isoformat())

@router.get('/knowledge/scenarios')
def scenarios(user=Depends(current_user),db=Depends(get_db)):
    from .models import GradeScenario
    return [record(x) for x in db.scalars(select(GradeScenario).where(GradeScenario.user_id==user.id).order_by(GradeScenario.created_at).limit(200))]


@router.get('/personal-tasks')
def tasks(user=Depends(current_user),db=Depends(get_db)):
    return [record(t) for t in db.scalars(select(PersonalTask).where(PersonalTask.user_id==user.id).order_by(PersonalTask.due_at))]


@router.post('/personal-tasks',status_code=201)
def create_task(body:PersonalTaskInput,user=Depends(current_user),db=Depends(get_db)):
    if body.subject_id:subject_for(db,user,body.subject_id)
    task=PersonalTask(user_id=user.id,**body.model_dump());db.add(task);db.commit();return record(task)


@router.patch('/personal-tasks/{task_id}')
def update_task(task_id:str,body:PersonalTaskUpdate,user=Depends(current_user),db=Depends(get_db)):
    task=db.scalar(select(PersonalTask).where(PersonalTask.id==task_id,PersonalTask.user_id==user.id))
    if not task:raise HTTPException(404,'Tarea personal no disponible')
    task.completed=body.completed;db.commit();return record(task)


@router.post('/knowledge/manual',status_code=201)
def manual_source(body:ManualKnowledge,request:Request,user=Depends(current_user),db=Depends(get_db)):
    from .academic_import import store_document
    subject_for(db,user,body.subject_id)
    import json
    content=body.text+'\n\nMetadatos declarados por el titular: '+json.dumps({'academic_year':body.academic_year,'weights':body.weights,'final_weights':body.final_weights},ensure_ascii=False)
    document=store_document(db,user,'aportacion-academica.md',body.title,body.subject_id,request.app.state.settings,content=content)
    source,counts=create_source_from_document(db,user,document,'general',body.applicable_year,body.academic_year,request.app.state.settings)
    if (body.weights or body.final_weights) and not db.scalar(select(AssessmentPolicy.id).where(AssessmentPolicy.source_id==source.id)):
        db.add(AssessmentPolicy(owner_id=user.id,subject_id=body.subject_id,source_id=source.id,scheme='manual',weights={k:str(v) for k,v in body.weights.items()},final_weights=[str(v) for v in body.final_weights],conditions={},rules_text=body.text))
    db.commit();return {'source':record(source),'message':'Aportación privada registrada, pendiente de validación. Las ponderaciones introducidas solo permiten simulaciones personales.'}
