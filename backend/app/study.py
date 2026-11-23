import hashlib,secrets,re
from datetime import datetime,timedelta,time
from decimal import Decimal,InvalidOperation
from fastapi import APIRouter,Depends,HTTPException
from sqlalchemy import select,or_
from .auth import current_user,get_db
from .db import utcnow,new_id
from .models import (Subject,LearnerProfile,LearnerSubject,CourseUnit,KnowledgeSource,StudySession,StudyPlan,
    CalendarEvent,Assignment,PersonalTask,PersonalScheduleSlot,LearningProgress,ActionRequest)
from .knowledge import subject_for,profile_for,personal_schedule
from .academic_import import normalize
from .learning_schemas import StudyInput,StudyAnswer,PlanInput,Availability
from .memory import MADRID,day_bounds
from .serializers import record
from .education import events_for,notify,assignments_for

router=APIRouter(prefix='/study',tags=['Estudio y planificación personal'])


def numeric_answer(value):
    value=re.sub(r'^\s*[a-zA-Z]\s*=\s*','',value).strip().replace(',','.')
    try:
        if re.fullmatch(r'-?\d+(?:\.\d+)?\s*/\s*-?\d+(?:\.\d+)?',value):
            a,b=value.split('/');n=Decimal(a.strip())/Decimal(b.strip())
        elif re.fullmatch(r'-?\d+(?:\.\d+)?',value):n=Decimal(value)
        else:return None
        return n if n.is_finite() else None
    except (InvalidOperation,ZeroDivisionError):return None


def exercise(topic,subject,level,index):
    normalized=__import__('unicodedata').normalize('NFKD',topic.lower())
    seed=index+level
    if 'matem' in normalize(subject) and ('logarit' in normalize(topic) or re.search(r'\blog\b',normalize(topic))):
        power=2+(seed%4);base=2 if level<3 else 3
        return {'id':new_id(),'kind':'numeric','prompt':f'Calcula log_{base}({base**power}).','expected':str(power),'misconception':str(base**power),
            'feedback':'El logaritmo pide el exponente, no el valor del argumento.','steps':f'{base}^{power} = {base**power}; por tanto log_{base}({base**power}) = {power}.','level':level}
    if ('matem' in subject.lower() and any(k in normalize(topic) for k in ('ecuaci','algebra','lineal'))) or 'ecuacion lineal' in normalize(topic):
        a=2+level;b=2+index;solution=2+(seed%5);c=a*solution+b
        return {'id':new_id(),'kind':'numeric','prompt':f'Resuelve {a}x + {b} = {c}.','expected':str(solution),'misconception':str(Decimal(c)/a),
            'feedback':'Resta primero el término independiente en ambos miembros; después divide entre el coeficiente de x.',
            'steps':f'{a}x = {c} − {b} = {c-b}; x = {c-b}/{a} = {solution}.','level':level}
    if 'fisica' in normalize(subject) and any(t in normalize(topic) for t in ('fuerza','dinamica')):
        mass=2+level;acceleration=2+index%5
        return {'id':new_id(),'kind':'numeric','prompt':f'Una masa de {mass} kg tiene aceleración {acceleration} m/s². Calcula la fuerza neta en N.','expected':str(mass*acceleration),
            'misconception':str(Decimal(mass)/acceleration),'feedback':'La segunda ley relaciona fuerza con masa por aceleración, F = m·a.',
            'steps':f'F = m·a = {mass}·{acceleration} = {mass*acceleration} N.','level':level}
    if 'tecnolog' in subject.lower() and any(t in normalize(topic) for t in ('electri','circuit','ohm')):
        resistance=2+level;current=2+index%4;voltage=resistance*current
        return {'id':new_id(),'kind':'numeric','prompt':f'Un resistor de {resistance} Ω está sometido a {voltage} V. ¿Qué intensidad circula, en A?','expected':str(current),
            'misconception':str(resistance*voltage),'feedback':'Despeja la intensidad en U = I·R: I = U/R.',
            'steps':f'I = U/R = {voltage}/{resistance} = {current} A.','level':level}
    return {'id':new_id(),'kind':'reflection','prompt':f'Explica con tus palabras la idea principal de «{topic}» y añade un ejemplo y una excepción.',
        'expected':None,'feedback':'Autoevaluación: comprueba definición, ejemplo, justificación y límites. El sistema no asigna una nota automática a esta respuesta abierta.',
        'steps':'Contrasta tu respuesta con los fragmentos y criterios de la fuente.','level':level}



def explanation(topic):
    topic=normalize(topic)
    if 'log' in topic:return 'Un logaritmo es un exponente: log_b(a) = x significa b^x = a. La base debe ser positiva y distinta de 1; el argumento, positivo. Identifica primero qué potencia produce el argumento y comprueba elevando la base al resultado.'
    if 'ecuaci' in topic or 'algebra' in topic:return 'Una ecuación expresa una igualdad que debe mantenerse al transformar ambos miembros. En ax + b = c, resta b en los dos lados y divide entre a si a es distinto de cero. Comprueba el resultado sustituyendo x en la igualdad original.'
    if 'fuerza' in topic or 'dinamica' in topic:return 'La fuerza neta es la suma vectorial de las fuerzas. Según F = m·a, una fuerza neta produce aceleración. Distingue masa (kg), aceleración (m/s²) y fuerza (N); una velocidad constante implica fuerza neta cero, no ausencia de fuerzas.'
    if any(k in topic for k in ('electri','ohm','circuit')):return 'La ley de Ohm relaciona tensión, intensidad y resistencia: U = I·R. Distingue voltios (V), amperios (A) y ohmios (Ω). Despeja la incógnita antes de sustituir. La relación lineal supone un componente óhmico en condiciones constantes.'
    return 'Empieza por una definición y organiza el tema en conceptos, relaciones, ejemplos y excepciones. Para este tema se ofrece una práctica de reflexión; contrasta el contenido con tus fuentes. La corrección automática está limitada a ecuaciones lineales, logaritmos, F = m·a y ley de Ohm.'

def public_session(session,db=None,user=None):
    out=record(session);out['explanation']=explanation(session.topic);out['exercises']=[{k:v for k,v in e.items() if k not in ('expected','misconception','steps','feedback')} for e in session.exercises]
    if db is not None and user is not None:
        out.update(study_evidence(db,user,session))
    return out


def study_evidence(db,user,session):
    from .relevance import score
    from .documents import retrieve_documents
    from .models import EvaluationCriterion
    source=db.scalar(select(KnowledgeSource).where(KnowledgeSource.id==session.source_id,KnowledgeSource.owner_id==user.id,KnowledgeSource.subject_id==session.subject_id)) if session.source_id else None
    units=list(db.scalars(select(CourseUnit).where(CourseUnit.owner_id==user.id,CourseUnit.subject_id==session.subject_id,CourseUnit.source_id==source.id))) if source else []
    matched=sorted([(score(session.topic,u.title,u.code),u) for u in units],key=lambda x:x[0],reverse=True)
    unit=matched[0][1] if matched and matched[0][0]>0 else None
    codes=[x for x in unit.criteria if isinstance(x,str)] if unit else []
    criteria=list(db.scalars(select(EvaluationCriterion).where(EvaluationCriterion.owner_id==user.id,EvaluationCriterion.source_id==source.id,EvaluationCriterion.code.in_(codes)))) if source and codes else []
    fragments=[d for d in retrieve_documents(db,user,session.topic,limit=12) if d['document_id']==source.document_id] if source and source.document_id else []
    return {'source':record(source) if source else None,'topic_alignment':{'unit':record(unit) if unit else None,'criteria':[record(c) for c in criteria],'fragments':[{k:d[k] for k in ('document_id','title','location','content')} for d in fragments[:3]],'status':'matched' if source else 'no_matching_source','note':'Solo se relacionan el tema y los criterios documentados; una fuente reciente no acredita por sí sola esa relación.'}}


def begin_study(db,user,args):
    subject=subject_for(db,user,args.subject_id)
    from .relevance import score
    from .documents import retrieve_documents
    sources=list(db.scalars(select(KnowledgeSource).where(KnowledgeSource.owner_id==user.id,KnowledgeSource.subject_id==subject.id).limit(100)))
    by_id={x.id:x for x in sources};by_doc={x.document_id:x for x in sources if x.document_id}
    units=list(db.scalars(select(CourseUnit).where(CourseUnit.owner_id==user.id,CourseUnit.subject_id==subject.id).limit(200)))
    matches=sorted([(score(args.topic,u.title,u.code),u) for u in units],key=lambda x:x[0],reverse=True)
    unit=matches[0][1] if matches and matches[0][0]>0 else None
    fragments=[d for d in retrieve_documents(db,user,args.topic,limit=12) if d['document_id'] in by_doc]
    source=by_id.get(unit.source_id) if unit else by_doc.get(fragments[0]['document_id']) if fragments else None
    previous=db.scalar(select(StudySession).where(StudySession.user_id==user.id,StudySession.subject_id==subject.id,StudySession.topic==args.topic).order_by(StudySession.updated_at.desc()))
    level=min(3,previous.level) if previous and previous.attempts else 1
    session=StudySession(user_id=user.id,subject_id=subject.id,topic=args.topic,mode=args.mode,level=level,source_id=source.id if source else None)
    session.exercises=[exercise(args.topic,subject.name,level,i) for i in range(3 if args.mode=='mock' else 1)]
    db.add(session);db.flush()
    return public_session(session,db,user)|{'provenance':'Práctica didáctica orientativa; no es un examen ni una calificación oficial.'}


@router.get('/sessions')
def sessions(user=Depends(current_user),db=Depends(get_db)):
    return [public_session(s,db,user) for s in db.scalars(select(StudySession).where(StudySession.user_id==user.id).order_by(StudySession.created_at.desc()).limit(30))]


@router.post('/sessions',status_code=201)
def create(body:StudyInput,user=Depends(current_user),db=Depends(get_db)):
    result=begin_study(db,user,body);db.commit();return result


@router.post('/sessions/{session_id}/answers')
def answer(session_id:str,body:StudyAnswer,user=Depends(current_user),db=Depends(get_db)):
    session=db.scalar(select(StudySession).where(StudySession.id==session_id,StudySession.user_id==user.id))
    if not session:raise HTTPException(404,'Sesión de estudio no disponible')
    previous=next((a for a in session.attempts if a['exercise_id']==body.exercise_id),None)
    if previous:return {'attempt':previous,'session':public_session(session,db,user)}
    ex=next((e for e in session.exercises if e['id']==body.exercise_id),None)
    if not ex:raise HTTPException(404,'Ejercicio no disponible')
    correct=None;feedback=ex['feedback']
    if ex['kind']=='numeric':
        parsed=numeric_answer(body.answer)
        if parsed is None:raise HTTPException(422,'Introduce una respuesta numérica o una fracción. Puedes corregirla antes de enviar')
        else:
            correct=abs(parsed-Decimal(ex['expected']))<Decimal('0.000001')
            feedback=('Resultado correcto. '+ex['steps']) if correct else ex['feedback']+' '+ex['steps']
    attempt={'exercise_id':ex['id'],'answer':body.answer,'correct':correct,'feedback':feedback,'at':utcnow().isoformat(),'official_grade':False}
    session.attempts=[*session.attempts,attempt]
    session.level=min(5,session.level+1) if correct else max(1,session.level-1) if correct is False else session.level
    subject=db.get(Subject,session.subject_id)
    if session.mode!='mock':session.exercises=[*session.exercises,exercise(session.topic,subject.name,session.level,len(session.exercises))]
    db.commit();return {'attempt':attempt,'session':public_session(session,db,user)}


@router.put('/availability')
def availability(body:list[Availability],user=Depends(current_user),db=Depends(get_db)):
    if len(body)>30:raise HTTPException(422,'Demasiadas franjas de disponibilidad')
    for i,a in enumerate(body):
        if any(a.weekday==b.weekday and a.starts<b.ends and b.starts<a.ends for b in body[:i]):raise HTTPException(422,'Las franjas se solapan')
    profile=profile_for(db,user);value=[a.model_dump() for a in body]
    if profile:profile.availability=value
    else:user.preferences={**user.preferences,'study_availability':value}
    db.commit();return {'ok':True}


def teaching_conflict(db,user,start,end):
    from .models import Schedule
    from .policy import group_ids
    if db.scalar(select(Schedule.id).where(Schedule.center_id==user.center_id,Schedule.group_id.in_(group_ids(db,user)),Schedule.weekday==start.weekday(),Schedule.starts<end.strftime('%H:%M'),Schedule.ends>start.strftime('%H:%M'))):return True
    schedule=personal_schedule(db,user,start.date().isoformat())
    return any(s['starts']<end.strftime('%H:%M') and s['ends']>start.strftime('%H:%M') for s in [*schedule['group_options'],*[s for s in schedule['lessons'] if s['is_break']]])


def plan_conflicts(db,user,plan):
    if plan.user_id!=user.id:raise HTTPException(404,'Plan no disponible')
    if plan.status!='draft':raise HTTPException(409,'El plan ya se ha revisado')
    conflicts=[]
    profile=profile_for(db,user);available=profile.availability if profile else user.preferences.get('study_availability',[])
    for session in plan.sessions:
        start=datetime.fromisoformat(session['starts_at']);end=datetime.fromisoformat(session['ends_at'])
        local_start=start.astimezone(MADRID);local_end=end.astimezone(MADRID)
        if start<=utcnow():conflicts.append({'title':'Una sesión propuesta ya ha pasado'})
        if not any(a['weekday']==local_start.weekday() and a['starts']<=local_start.strftime('%H:%M') and a['ends']>=local_end.strftime('%H:%M') and local_start.date()==local_end.date() for a in available):conflicts.append({'title':'La disponibilidad ha cambiado'})
        if profile and teaching_conflict(db,user,local_start,local_end):conflicts.append({'title':'Conflicto con un bloque del horario académico'})
        events=events_for(db,user,start=start,end=end)
        conflicts.extend({'title':e['title']} for e in events if e['status']=='published' and datetime.fromisoformat(e['starts_at'])<end and datetime.fromisoformat(e['ends_at'])>start)
    return conflicts


def prepare_plan(db,user,args):
    profile=profile_for(db,user)
    available=profile.availability if profile else user.preferences.get('study_availability',[])
    if not available:raise HTTPException(422,'Configura primero tu disponibilidad en Estudio y planificación; no se supondrán horas libres')
    if args.start_day:day_bounds(args.start_day)
    start_date=datetime.fromisoformat(args.start_day).date() if args.start_day else utcnow().astimezone(MADRID).date()
    selected=set(db.scalars(select(LearnerSubject.subject_id).where(LearnerSubject.user_id==user.id,LearnerSubject.active.is_(True))))
    from .learning_tools import subjects_for
    allowed={s['id'] for s in subjects_for(db,user)}
    subject_stmt=select(Subject).where(Subject.center_id==user.center_id,Subject.id.in_(allowed))
    if selected:subject_stmt=subject_stmt.where(Subject.id.in_(selected))
    if args.subject_id:subject_for(db,user,args.subject_id);subject_stmt=subject_stmt.where(Subject.id==args.subject_id)
    subjects=list(db.scalars(subject_stmt.order_by(Subject.name)))
    if not subjects:raise HTTPException(422,'No hay asignaturas disponibles para organizar el estudio')
    units=list(db.scalars(select(CourseUnit).where(CourseUnit.owner_id==user.id,CourseUnit.subject_id.in_([s.id for s in subjects])).order_by(CourseUnit.term,CourseUnit.created_at)))
    progress={p.unit_id:p for p in db.scalars(select(LearningProgress).where(LearningProgress.user_id==user.id))}
    topics=[{'subject_id':u.subject_id,'title':u.title,'unit_id':u.id,'source_id':u.source_id} for u in units if u.id not in progress or progress[u.id].state!='mastered']
    deadlines=[]
    for e in events_for(db,user,kind='exam',start=utcnow(),end=utcnow()+timedelta(days=21)):
        if e['status']=='published' and e['subject_id'] in [s.id for s in subjects]:deadlines.append({'subject_id':e['subject_id'],'title':'Preparación: '+e['title'],'due_at':e['starts_at']})
    for task in db.scalars(select(PersonalTask).where(PersonalTask.user_id==user.id,PersonalTask.completed.is_(False),PersonalTask.due_at>utcnow()).order_by(PersonalTask.due_at)):
        if task.subject_id in [s.id for s in subjects]:deadlines.append({'subject_id':task.subject_id,'title':'Preparar tarea: '+task.title,'due_at':task.due_at.isoformat()})
    for task in assignments_for(db,user):
        if task['subject_id'] in [s.id for s in subjects] and not task.get('submission') and datetime.fromisoformat(task['due_at'])>utcnow():deadlines.append({'subject_id':task['subject_id'],'title':'Preparar entrega: '+task['title'],'due_at':task['due_at']})
    topics=sorted(deadlines,key=lambda d:d['due_at'])+topics
    if not topics:topics=[{'subject_id':s.id,'title':'Repaso de '+s.name} for s in subjects]
    sessions=[];cursor_topic=0
    for offset in range(args.days):
        day=start_date+timedelta(days=offset)
        for frame in [f for f in available if f['weekday']==day.weekday()]:
            start=datetime.combine(day,time.fromisoformat(frame['starts']),MADRID);end=datetime.combine(day,time.fromisoformat(frame['ends']),MADRID)
            while start+timedelta(minutes=args.session_minutes)<=end and len(sessions)<args.max_sessions:
                finish=start+timedelta(minutes=args.session_minutes)
                clashes=events_for(db,user,start=start,end=finish)
                busy=any(e['status']=='published' and datetime.fromisoformat(e['starts_at'])<finish and datetime.fromisoformat(e['ends_at'])>start for e in clashes)
                busy=busy or teaching_conflict(db,user,start,finish)
                if start>utcnow() and not busy:
                    topic=topics[cursor_topic%len(topics)];cursor_topic+=1
                    if not topic.get('due_at') or finish<datetime.fromisoformat(topic['due_at']):sessions.append(dict(topic,starts_at=start.isoformat(),ends_at=finish.isoformat()))
                start=finish+timedelta(minutes=10)
            if len(sessions)>=args.max_sessions:break
        if len(sessions)>=args.max_sessions:break
    if not sessions:raise HTTPException(409,'No hay huecos compatibles con tu disponibilidad y calendario; amplía las franjas')
    plan=StudyPlan(user_id=user.id,title='Plan de estudio personal',sessions=sessions)
    db.add(plan);db.flush()
    action=ActionRequest(center_id=user.center_id,user_id=user.id,tool='save_study_plan',arguments={'plan_id':plan.id},expires_at=utcnow()+timedelta(hours=24))
    db.add(action);db.flush()
    return {'status':'pending_confirmation','tool':'create_study_plan','action':record(action),'result':record(plan),'conflicts':[]}


def save_plan(db,user,plan):
    conflicts=plan_conflicts(db,user,plan)
    if conflicts:raise HTTPException(409,'El calendario ha cambiado y el plan tiene conflictos')
    ids=[]
    for session in plan.sessions:
        event=CalendarEvent(center_id=user.center_id,owner_id=user.id,title=session['title'][:180],description='Sesión personal de estudio confirmada. '+('Unidad: '+session.get('unit_id','') if session.get('unit_id') else ''),kind='reminder',visibility='personal',starts_at=datetime.fromisoformat(session['starts_at']),ends_at=datetime.fromisoformat(session['ends_at']),source='Plan de estudio personal confirmado')
        db.add(event);db.flush();ids.append(event.id)
    plan.status='confirmed';plan.event_ids=ids
    return {'plan_id':plan.id,'event_ids':ids,'count':len(ids)}


@router.get('/plans')
def plans(user=Depends(current_user),db=Depends(get_db)):
    return [record(p) for p in db.scalars(select(StudyPlan).where(StudyPlan.user_id==user.id).order_by(StudyPlan.created_at.desc()).limit(30))]


@router.post('/plans',status_code=201)
def create_plan(body:PlanInput,user=Depends(current_user),db=Depends(get_db)):
    result=prepare_plan(db,user,body);db.commit();return result
