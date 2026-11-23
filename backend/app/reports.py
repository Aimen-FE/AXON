from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select, delete
from .auth import current_user,get_db
from .db import utcnow,new_id
from .models import CalendarEvent,Document,Schedule,Group,ReviewReport,Center,BathroomPass,Session,LoginAttempt,ActionRequest,User,Assignment
from .policy import require_role,audit
from .schemas import ReviewDecision
from .serializers import record
from .memory import MADRID
from .education import notify

router=APIRouter(prefix='/reports',tags=['Revisión administrativa'])


def build_report(db,center_id,trigger='manual',review_day=None):
    findings=[]
    def add(kind,title,detail,correction=None):
        findings.append({'id':new_id(),'kind':kind,'title':title,'detail':detail,'status':'pending','correction':correction})
    events=list(db.scalars(select(CalendarEvent).where(CalendarEvent.center_id==center_id,CalendarEvent.visibility!='personal',CalendarEvent.status=='published').order_by(CalendarEvent.starts_at)))
    for i,event in enumerate(events):
        for other in events[:i]:
            same=event.group_id==other.group_id and event.visibility==other.visibility
            if same and event.starts_at==other.starts_at and event.title.casefold()==other.title.casefold():
                add('duplicate','Evento académico duplicado',f'{event.title}: {event.starts_at.astimezone(MADRID).strftime("%d/%m/%Y %H:%M")}',
                    {'tool':'cancel_event','arguments':{'event_id':event.id,'version':event.version}})
            elif same and event.group_id and event.starts_at<other.ends_at and other.starts_at<event.ends_at:
                add('conflict','Eventos de grupo solapados',f'{other.title} / {event.title}. Revisa las fechas antes de modificar el calendario.')
    schedules=list(db.scalars(select(Schedule).where(Schedule.center_id==center_id)))
    for i,s in enumerate(schedules):
        for o in schedules[:i]:
            if s.weekday==o.weekday and s.starts<o.ends and o.starts<s.ends and (s.group_id==o.group_id or s.teacher_id==o.teacher_id or (s.classroom_id and s.classroom_id==o.classroom_id)):
                add('conflict','Sesiones de horario incompatibles',f'Día {s.weekday+1}, {s.starts}–{s.ends}; revisa grupo, docente y aula.')
    for group in db.scalars(select(Group).where(Group.center_id==center_id)):
        present={s.weekday for s in schedules if s.group_id==group.id}
        if len(present)<5:
            add('missing','Horario incompleto',f'{group.name}: faltan sesiones en {5-len(present)} días lectivos. No se han inventado clases.')
    docs=list(db.scalars(select(Document).where(Document.center_id==center_id,Document.access!='personal')))
    for doc in docs:
        if doc.status=='provisional':
            add('validation','Documento pendiente de validación',f'{doc.title}, versión {doc.version}. La conversación no lo convierte en fuente oficial.',
                {'tool':'validate_document','arguments':{'document_id':doc.id,'status':'validated'}})
        elif doc.updated_at<utcnow()-timedelta(days=365):
            add('stale','Documento con revisión antigua',f'{doc.title}: comprueba si necesita una nueva versión.')
    report=ReviewReport(center_id=center_id,findings=findings[:300],trigger=trigger,review_day=review_day)
    db.add(report)
    db.flush()
    return report


@router.get('')
def reports(user=Depends(current_user),db=Depends(get_db)):
    require_role(user,'admin')
    return [record(x) for x in db.scalars(select(ReviewReport).where(ReviewReport.center_id==user.center_id).order_by(ReviewReport.created_at.desc()).limit(30))]


@router.post('',status_code=201)
def run(user=Depends(current_user),db=Depends(get_db)):
    require_role(user,'admin')
    obj=build_report(db,user.center_id)
    audit(db,user,'review_generated',obj,{'count':len(obj.findings)})
    db.commit()
    return record(obj)


@router.post('/{report_id}/findings/{finding_id}')
def decision(report_id:str,finding_id:str,body:ReviewDecision,user=Depends(current_user),db=Depends(get_db)):
    require_role(user,'admin')
    obj=db.scalar(select(ReviewReport).where(ReviewReport.id==report_id,ReviewReport.center_id==user.center_id))
    if not obj: raise HTTPException(404,'Informe no disponible')
    entries=[dict(x) for x in obj.findings]
    item=next((x for x in entries if x['id']==finding_id),None)
    if not item: raise HTTPException(404,'Hallazgo no disponible')
    if item['status']!='pending': raise HTTPException(409,'Este hallazgo ya se ha revisado')
    item['status']=body.decision
    action=None
    if body.decision=='accepted' and item.get('correction'):
        from .tools import run_tool
        from .config import Settings
        proposed=run_tool(db,user,item['correction']['tool'],item['correction']['arguments'],Settings.from_env())
        action=proposed.get('action')
        item['action_id']=action['id'] if action else None
    obj.findings=entries
    audit(db,user,'finding_reviewed',obj,{'finding_id':finding_id,'decision':body.decision})
    db.commit()
    return {'report':record(obj),'action':action,'message':'Corrección preparada; confirma la propuesta para aplicarla' if action else 'Revisión registrada; no se han cambiado datos académicos'}


def daily_maintenance(db):
    """Una ejecución por fecha local y centro. Conserva las conversaciones originales."""
    now=utcnow()
    day=now.astimezone(MADRID).date().isoformat()
    db.execute(delete(Session).where(Session.expires_at<now))
    db.execute(delete(LoginAttempt).where(LoginAttempt.created_at<now-timedelta(days=1)))
    for action in db.scalars(select(ActionRequest).where(ActionRequest.status=='pending',ActionRequest.expires_at<now)):
        action.status='expired'
    for center in db.scalars(select(Center)):
        retention=int(center.settings.get('bathroom_retention_days',14))
        # Active passes older than the retention horizon also expire; no indefinite tracking.
        db.execute(delete(BathroomPass).where(BathroomPass.center_id==center.id,BathroomPass.left_at<now-timedelta(days=retention)))
        if not center.settings.get('automation_enabled',True): continue
        if not db.scalar(select(ReviewReport.id).where(ReviewReport.center_id==center.id,ReviewReport.review_day==day)):
            report=build_report(db,center.id,'scheduled',day)
            for admin_id in db.scalars(select(User.id).where(User.center_id==center.id,User.role=='admin',User.active.is_(True))):
                notify(db,admin_id,'Revisión académica diaria',f'{len(report.findings)} hallazgos disponibles en Informes','event',f'review:{center.id}:{day}:{admin_id}')
    from .models import Conversation
    for owner in db.scalars(select(User).where(User.active.is_(True))):
        days=owner.preferences.get('conversation_retention_days')
        if type(days) is int and 30<=days<=3650:db.execute(delete(Conversation).where(Conversation.user_id==owner.id,Conversation.updated_at<now-timedelta(days=days)))
    from .notifications import reminders
    from .models import SemanticVector,Message,Memory
    db.execute(delete(SemanticVector).where(SemanticVector.entity=='message',~SemanticVector.record_id.in_(select(Message.id))))
    db.execute(delete(SemanticVector).where(SemanticVector.entity=='memory',~SemanticVector.record_id.in_(select(Memory.id))))
    reminders(db)
    db.commit()
