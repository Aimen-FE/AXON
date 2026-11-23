"""Bounded plans. Each step authorizes afresh and commits once; write steps are never retried."""
import asyncio
import re
import time
from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, update
from .auth import current_user, get_db
from .db import utcnow
from .models import AgentRun, AgentStep, User, ActionRequest, Memory, MemoryAnnotation, CalendarEvent, PersonalTask, StudyPlan
from .serializers import record

router=APIRouter(prefix='/agent',tags=['Planes privados del agente'])
LABELS={
    'query_exams':'Consultar exámenes publicados','get_pending':'Revisar tareas y recuerdos pendientes',
    'get_my_schedule':'Comprobar el horario disponible','get_study_context':'Relacionar temarios y exámenes',
    'search_documents':'Recuperar fuentes autorizadas','query_knowledge':'Consultar criterios y unidades',
    'create_study_plan':'Preparar sesiones sin solapamientos','search_public':'Consultar una fuente pública',
    'research_sources':'Contrastar fuentes públicas','calculate_math':'Calcular y comprobar el resultado',
    'search_semantic_memory':'Recuperar recuerdos relevantes','save_memory':'Guardar el recuerdo privado',
}
SAFE_RETRY={'query_exams','query_calendar','query_assignments','query_schedule','query_subjects',
    'get_my_schedule','get_pending','get_teachers','get_subjects','get_school_information','query_knowledge',
    'get_study_context','search_documents','search_memory','search_semantic_memory','search_public','research_sources','get_notifications'}

def advanced_plan(db,user,text):
    from .agent import norm
    from .learning_agent import resolve_subject
    s=norm(text)
    # Explicit math syntax; arbitrary prose and Python are never fed to an interpreter.
    operations={'calcula':'evaluate','simplifica':'simplify','resuelve':'solve','deriva':'differentiate','integra':'integrate'}
    match=re.match(r'^(?:axon[, :]+)?(calcula|simplifica|resuelve|deriva|integra)\s*:?\s*(.+)$',text.strip(),re.I)
    numeric_syntax=bool(match and re.fullmatch(r'[0-9xyzt\s.+*/^(),-]+',re.sub(r'\b(sqrt|sin|cos|tan|log|exp|abs|pi|e)\b','',match[2],flags=re.I)))
    if match and numeric_syntax and not any(word in s for word in ('nota','evaluacion','recuperacion','necesito sacar')):
        return {'calls':[('calculate_math',{'operation':operations[match[1].lower()],'expression':match[2]})]}
    if any(phrase in s for phrase in ('busca por significado','busqueda semantica','recuerdos relacionados')):
        query=re.sub(r'^.*?(?:significado|semántica|relacionados)\s*:?\s*','',text,flags=re.I)
        if len(query.strip())<2:return {'clarification':'Indica qué quieres recuperar por su significado.'}
        return {'calls':[('search_semantic_memory',{'query':query[:300]})]}
    # Mixed educational requests. Internet queries must be supplied separately, not inferred from private exams.
    axes=sum(bool(re.search(pattern,s)) for pattern in (r'examen',r'tareas|pendientes',r'busca|informacion|fuentes',r'organiza|planifica|semana'))
    if axes<2:return None
    subject=resolve_subject(db,user,text)
    subject_id=subject.id if subject else None
    calls=[]
    if 'examen' in s:calls.append(('query_exams',{}))
    if re.search(r'tareas|pendientes',s):calls.append(('get_pending',{}))
    organize=bool(re.search(r'organiza|planifica',s))
    if organize:calls.append(('get_my_schedule',{}))
    if re.search(r'busca|informacion|fuentes|preparar',s):
        calls.append(('get_study_context',{'subject_id':subject_id,'query':text[:600]}))
        calls.append(('search_documents',{'query':subject.name if subject else '', '_from_exams':not bool(subject)}))
    external=re.search(r'(?:en internet|en la web)\s+sobre\s+(.+?)(?:;|$)',text,re.I)
    if external:calls.append(('research_sources',{'query':external[1][:250],'consent':True}))
    if organize:calls.append(('create_study_plan',{'subject_id':subject_id}))
    return {'calls':calls[:8],'force_confirmation':True,'compound':True}

def run_record(db,run):
    return dict(record(run),steps=[record(s) for s in db.scalars(select(AgentStep).where(AgentStep.run_id==run.id).order_by(AgentStep.position))])

def settle(db,run):
    steps=list(db.scalars(select(AgentStep).where(AgentStep.run_id==run.id).order_by(AgentStep.position)))
    for step in steps:
        if step.status=='pending_confirmation' and step.action_id:
            action=db.scalar(select(ActionRequest).where(ActionRequest.id==step.action_id,ActionRequest.user_id==run.user_id))
            if action and action.status=='pending' and action.expires_at<=utcnow():action.status='expired'
            if action and action.status=='approved':
                step.verified=verify_result(db,run.user_id,action.tool,action.result)
                step.status='completed' if step.verified else 'verification_incomplete';step.summary='Acción confirmada y comprobada' if step.verified else 'Acción confirmada; comprobación incompleta. No se repetirá automáticamente'
            elif action and action.status in ('rejected','expired'):
                step.status=action.status;step.summary='Propuesta rechazada' if action.status=='rejected' else 'Propuesta caducada'
    if run.status in ('planned','running') and run.deadline_at<utcnow():
        for step in steps:
            if step.status in ('planned','running'):step.status='interrupted';step.summary='Ejecución interrumpida. Las escrituras no se repiten automáticamente'
        run.status='partial'
    elif run.status in ('awaiting_confirmation','completed','partial'):
        statuses=[s.status for s in steps]
        run.status='awaiting_confirmation' if 'pending_confirmation' in statuses else 'partial' if any(s not in ('completed',) for s in statuses) else 'completed'
    return steps

def verify_result(db,user_id,tool,result):
    if not isinstance(result,(dict,list)):return False
    if tool in ('create_event','publish_exam','update_event','cancel_event'):
        obj=db.get(CalendarEvent,result.get('id'));return bool(obj and obj.owner_id==user_id)
    if tool=='save_memory':return bool(db.scalar(select(Memory.id).where(Memory.id==result.get('id'),Memory.user_id==user_id)))
    if tool=='create_personal_task':return bool(db.scalar(select(PersonalTask.id).where(PersonalTask.id==result.get('id'),PersonalTask.user_id==user_id)))
    if tool=='save_study_plan':
        plan=db.scalar(select(StudyPlan).where(StudyPlan.id==result.get('plan_id'),StudyPlan.user_id==user_id))
        if not plan:return False
        return plan.status=='confirmed' and all(db.scalar(select(CalendarEvent.id).where(CalendarEvent.id==ident,CalendarEvent.owner_id==user_id)) for ident in plan.event_ids)
    return True

def perform(factory,user_id,name,args,settings,force_confirmation,message_id):
    from .tools import run_tool
    with factory() as db:
        user=db.get(User,user_id)
        if not user or not user.active:raise HTTPException(403,'La cuenta ya no está activa')
        result=run_tool(db,user,name,args,settings,force_confirmation=force_confirmation)
        if name=='save_memory' and result.get('result'):
            db.add(MemoryAnnotation(user_id=user.id,memory_id=result['result']['id'],source_message_id=message_id,
                provenance='Guardado por petición explícita en el mensaje original',state='provisional'))
        verified=verify_result(db,user_id,name,result.get('result',{})) if result['status']=='completed' else False
        db.commit()
        return result,verified

async def execute(app,user,conversation_id,message_id,proposed):
    factory=app.state.session_factory;settings=app.state.settings
    calls=proposed['calls']
    if not 1<=len(calls)<=8:raise HTTPException(422,'El plan supera el límite de ocho pasos')
    from .tools import parse_tool
    with factory() as db:
        run=AgentRun(user_id=user.id,center_id=user.center_id,conversation_id=conversation_id,message_id=message_id,
            deadline_at=utcnow()+timedelta(seconds=75),max_steps=len(calls),planner=proposed.get('planner','structured'))
        db.add(run);db.flush()
        for position,(name,args) in enumerate(calls,1):
            if name not in LABELS:
                from .tools import CATALOG
                label=CATALOG[name].description if name in CATALOG else 'Comprobar herramienta'
            else:label=LABELS[name]
            db.add(AgentStep(run_id=run.id,position=position,tool=name,label=label,dependencies=list(range(1,position)) if name=='create_study_plan' else []))
        db.commit();run_id=run.id
    results=[];summaries=[]
    for position,(name,original_args) in enumerate(calls,1):
        with factory() as db:
            run=db.get(AgentRun,run_id)
            db.refresh(run)
            if run.cancel_requested or utcnow()>=run.deadline_at:
                for step in db.scalars(select(AgentStep).where(AgentStep.run_id==run_id,AgentStep.status=='planned')):
                    step.status='cancelled' if run.cancel_requested else 'skipped';step.summary='Cancelado antes de ejecutar' if run.cancel_requested else 'Límite total de tiempo alcanzado'
                run.status='cancelled' if run.cancel_requested else 'partial';db.commit();break
            run.status='running'
            step=db.scalar(select(AgentStep).where(AgentStep.run_id==run_id,AgentStep.position==position))
            step.status='running';db.commit();step_id=step.id
        args=dict(original_args)
        if args.pop('_from_exams',False):
            exams=next((r.get('result',[]) for r in results if r['tool']=='query_exams' and r['status']=='completed'),[])
            words=' '.join(e.get('syllabus','') for e in exams[:3]).strip()
            args['query']=words[:300] or 'temario estudio examen'
        started=time.monotonic();error=None;result=None;verified=False;attempts=0
        for attempt in range(2 if name in SAFE_RETRY else 1):
            attempts=attempt+1
            try:
                # Validate independently of planner and authorize again in the tool transaction.
                parse_tool(user,name,args)
                result,verified=await asyncio.to_thread(perform,factory,user.id,name,args,settings,
                    proposed.get('force_confirmation',False),message_id)
                break
            except asyncio.CancelledError:
                # A disconnected request cannot cause an automatic write retry. Persisted steps remain inspectable.
                raise
            except HTTPException as exc:
                error=exc
                if exc.status_code not in (502,503,504) or name not in SAFE_RETRY:break
                with factory() as db:
                    current=db.get(AgentRun,run_id)
                    if current.cancel_requested or utcnow()+timedelta(seconds=2)>=current.deadline_at:break
                await asyncio.sleep(.15)
            except Exception:
                error=HTTPException(500,'La herramienta no pudo completar este paso');break
        with factory() as db:
            step=db.get(AgentStep,step_id);step.attempts=attempts;step.duration_ms=round((time.monotonic()-started)*1000)
            if result is not None:
                step.status=result['status'];step.verified=verified
                if result.get('action'):step.action_id=result['action']['id']
                value=result.get('result')
                count=len(value) if isinstance(value,list) else None
                step.summary='Propuesta preparada; falta confirmación' if step.action_id else f'{count} registro autorizado recuperado' if count==1 else f'{count} registros autorizados recuperados' if count is not None else 'Resultado comprobado' if verified else 'Resultado parcial o integración no disponible'
                if result['status']=='unavailable':step.summary='Integración no disponible; no se simula una consulta real'
                if result['status']=='completed' and (not verified or isinstance(value,dict) and (value.get('status')=='missing_information' or value.get('failures'))):
                    step.status='incomplete';step.verified=False;step.summary='La herramienta devolvió información incompleta. Revisa el resultado y sus fuentes'
                if result.get('conflicts'):step.summary='Propuesta con conflictos; revísala antes de confirmar'
                result['query']=args.get('query','');results.append(result)
            else:
                step.status='failed';step.error_code=str(error.status_code);step.summary=str(error.detail)[:450] if isinstance(error.detail,str) else 'Argumentos inválidos; revisa los datos'
                summaries.append(step.label+': '+step.summary)
            db.commit()
    with factory() as db:
        run=db.get(AgentRun,run_id)
        if run.status!='cancelled':
            states=[s.status for s in db.scalars(select(AgentStep).where(AgentStep.run_id==run.id))]
            run.status='awaiting_confirmation' if 'pending_confirmation' in states else 'partial' if any(s!='completed' for s in states) else 'completed'
        db.commit();out=run_record(db,run)
    return results,out,summaries

@router.get('/runs')
def runs(conversation_id:str|None=None,user=Depends(current_user),db=Depends(get_db)):
    stmt=select(AgentRun).where(AgentRun.user_id==user.id)
    if conversation_id:stmt=stmt.where(AgentRun.conversation_id==conversation_id)
    result=[]
    for run in db.scalars(stmt.order_by(AgentRun.created_at.desc()).limit(30)):
        settle(db,run);result.append(run_record(db,run))
    db.commit();return result

@router.get('/runs/{run_id}')
def detail(run_id:str,user=Depends(current_user),db=Depends(get_db)):
    run=db.scalar(select(AgentRun).where(AgentRun.id==run_id,AgentRun.user_id==user.id))
    if not run:raise HTTPException(404,'Plan privado no disponible')
    settle(db,run);db.commit();return run_record(db,run)

@router.post('/runs/{run_id}/cancel')
def cancel(run_id:str,user=Depends(current_user),db=Depends(get_db)):
    run=db.scalar(select(AgentRun).where(AgentRun.id==run_id,AgentRun.user_id==user.id))
    if not run:raise HTTPException(404,'Plan privado no disponible')
    if run.status not in ('planned','running'):raise HTTPException(409,'El plan ya terminó. Rechaza las propuestas pendientes en Confirmaciones')
    run.cancel_requested=True;db.commit();return {'cancel_requested':True,'note':'Se detendrá antes del siguiente paso; el paso en curso puede terminar'}
