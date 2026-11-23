"""Persistent bounded jobs. A claimed slot is never replayed automatically after a crash."""
from datetime import timedelta
from fastapi import APIRouter,Depends,HTTPException,Request
from sqlalchemy import select,update
from .auth import current_user,get_db
from .db import utcnow
from .models import ScheduledJob,JobExecution,User,Center,Document,Notification
from .advanced_schemas import AutomationInput,AutomationUpdate
from .schemas import Input
from pydantic import AwareDatetime
from .serializers import record
from .extensions import enabled,require_module
from .policy import require_role,audit

router=APIRouter(prefix='/automations',tags=['Automatizaciones persistentes'])
ADMIN_KINDS={'academic_report','stale_documents','backup'}

def own(db,user,ident):
    job=db.scalar(select(ScheduledJob).where(ScheduledJob.id==ident,ScheduledJob.user_id==user.id))
    if not job:raise HTTPException(404,'Automatización privada no disponible')
    return job

@router.get('')
def list_jobs(user=Depends(current_user),db=Depends(get_db)):
    return [dict(record(j),executions=[record(e) for e in db.scalars(select(JobExecution).where(JobExecution.job_id==j.id).order_by(JobExecution.created_at.desc()).limit(10))]) for j in db.scalars(select(ScheduledJob).where(ScheduledJob.user_id==user.id).order_by(ScheduledJob.created_at.desc()).limit(50))]

@router.post('',status_code=201)
def create(body:AutomationInput,user=Depends(current_user),db=Depends(get_db)):
    if body.kind in ADMIN_KINDS:require_role(user,'admin')
    if body.next_run_at<utcnow()-timedelta(minutes=1):raise HTTPException(422,'Elige una primera ejecución futura')
    if len(list(db.scalars(select(ScheduledJob.id).where(ScheduledJob.user_id==user.id,ScheduledJob.cancelled.is_(False)))))>=20:raise HTTPException(422,'Máximo veinte automatizaciones activas o pausadas')
    job=ScheduledJob(user_id=user.id,center_id=user.center_id,**body.model_dump());db.add(job);db.flush()
    if body.kind in ADMIN_KINDS:audit(db,user,'automation_created',job,{'kind':body.kind})
    db.commit();return record(job)

@router.patch('/{job_id}')
def toggle(job_id:str,body:AutomationUpdate,user=Depends(current_user),db=Depends(get_db)):
    job=own(db,user,job_id)
    if job.cancelled:raise HTTPException(409,'Esta automatización está cancelada')
    job.enabled=body.enabled;db.commit();return record(job)

@router.delete('/{job_id}')
def cancel(job_id:str,user=Depends(current_user),db=Depends(get_db)):
    job=own(db,user,job_id);job.cancelled=True;job.enabled=False;db.commit();return record(job)

class RunInput(Input):
    scheduled_for:AwareDatetime

def work(db,user,job,settings):
    from .education import events_for,notify
    from .notifications import DEFAULT
    now=utcnow();summary=''
    if job.kind in ADMIN_KINDS:require_role(user,'admin')
    if job.kind=='upcoming_exams':
        exams=[e for e in events_for(db,user,'exam',now,now+timedelta(days=7)) if e['status']=='published']
        summary=f'{len(exams)} exámenes publicados en los próximos siete días. Consulta Exámenes para revisar sus fechas.'
    elif job.kind=='schedule_conflicts':
        events=[e for e in events_for(db,user,start=now,end=now+timedelta(days=7)) if e['status']=='published']
        count=sum(a['starts_at']<b['ends_at'] and b['starts_at']<a['ends_at'] for i,a in enumerate(events) for b in events[:i])
        summary=f'{count} posibles solapamientos en tu calendario de los próximos siete días.'
    elif job.kind=='stale_documents':
        count=len(list(db.scalars(select(Document.id).where(Document.center_id==user.center_id,Document.access!='personal',Document.updated_at<now-timedelta(days=365)))))
        summary=f'{count} documentos institucionales necesitan una revisión de vigencia. No se han modificado.'
    elif job.kind=='academic_report':
        from .reports import build_report
        report=build_report(db,user.center_id,'scheduled');summary=f'Informe preparado: {len(report.findings)} hallazgos. Revisa Informes antes de aplicar cambios.'
        audit(db,user,'scheduled_report_generated',report)
    elif job.kind=='backup':
        # The caller executes backup outside the database transaction.
        from .operations import protected_backup
        meta=protected_backup(settings);summary='Copia creada y restauración verificada: '+meta['name']
    else:raise HTTPException(422,'Tipo de automatización desconocido')
    prefs={**DEFAULT,**user.preferences.get('notification_options',{})}
    if prefs['enabled']:notify(db,user.id,job.title,summary,'reminder',f'automation:{job.id}:{job.next_run_at.isoformat()}')
    return summary

def execute_job(factory,settings,job_id,slot,manual=False):
    with factory() as db:
        job=db.get(ScheduledJob,job_id)
        if not job or job.cancelled or not job.enabled:return {'status':'skipped'}
        user=db.get(User,job.user_id);center=db.get(Center,job.center_id)
        if not user or not user.active or not center.settings.get('automation_enabled',True) or not enabled(db,user,'scheduler'):return {'status':'paused_by_policy'}
        if job.kind in ADMIN_KINDS and user.role!='admin':return {'status':'permission_changed'}
        next_slot=max(utcnow(),slot)+timedelta(hours=job.interval_hours)
        changed=db.execute(update(ScheduledJob).where(ScheduledJob.id==job.id,ScheduledJob.next_run_at==slot,ScheduledJob.enabled.is_(True),ScheduledJob.cancelled.is_(False)).values(next_run_at=next_slot)).rowcount
        if not changed:return {'status':'already_claimed'}
        execution=JobExecution(job_id=job.id,scheduled_for=slot);db.add(execution);db.commit();execution_id=execution.id
    try:
        with factory() as db:
            job=db.get(ScheduledJob,job_id);user=db.get(User,job.user_id)
            # Role/module/status are rechecked after claiming and before any effects.
            if not user.active or job.cancelled or not job.enabled or not enabled(db,user,'scheduler'):raise HTTPException(409,'Automatización desactivada antes de ejecutar')
            summary=work(db,user,job,settings)
            execution=db.get(JobExecution,execution_id);execution.status='completed';execution.summary=summary;db.commit()
            return record(execution)
    except Exception as exc:
        with factory() as db:
            execution=db.get(JobExecution,execution_id);execution.status='failed'
            execution.summary=str(exc.detail)[:300] if isinstance(exc,HTTPException) and isinstance(exc.detail,str) else 'La ejecución no pudo completarse. No se reintenta esta franja automáticamente.'
            db.commit();return record(execution)

@router.post('/{job_id}/run')
def run(job_id:str,body:RunInput,request:Request,user=Depends(current_user),db=Depends(get_db)):
    job=own(db,user,job_id)
    if job.kind in ADMIN_KINDS:require_role(user,'admin')
    db.commit()
    return execute_job(request.app.state.session_factory,request.app.state.settings,job.id,body.scheduled_for,True)

def tick(factory,settings):
    with factory() as db:
        # A crash after claiming is visible, never silently retried as a write.
        for execution in db.scalars(select(JobExecution).where(JobExecution.status=='running',JobExecution.created_at<utcnow()-timedelta(minutes=20))):
            execution.status='interrupted';execution.summary='Interrumpido por reinicio; revisa el resultado antes de ejecutar de nuevo'
        jobs=[(j.id,j.next_run_at) for j in db.scalars(select(ScheduledJob).where(ScheduledJob.enabled.is_(True),ScheduledJob.cancelled.is_(False),ScheduledJob.next_run_at<=utcnow()).order_by(ScheduledJob.next_run_at).limit(20))];db.commit()
    return [execute_job(factory,settings,ident,slot) for ident,slot in jobs]
