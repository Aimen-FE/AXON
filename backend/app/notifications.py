"""Avisos privados configurables, independientes de la revisión institucional."""
from datetime import timedelta
from fastapi import APIRouter,Depends
from sqlalchemy import select
from .auth import current_user,get_db,public_user
from .db import utcnow
from .models import User,PersonalTask,ActionRequest
from .learning_schemas import NotificationPreferences
from .education import events_for,assignments_for,notify

router=APIRouter(prefix='/notification-preferences',tags=['Preferencias de avisos'])
DEFAULT={'enabled':True,'advance_hours':24,'frequency':'daily','priority':'all'}

@router.get('')
def preferences(user=Depends(current_user)):
    return {**DEFAULT,**user.preferences.get('notification_options',{})}

@router.put('')
def save(body:NotificationPreferences,user=Depends(current_user),db=Depends(get_db)):
    user.preferences={**user.preferences,'notification_options':body.model_dump()};db.commit()
    return body.model_dump()

def reminders(db):
    now=utcnow()
    for user in db.scalars(select(User).where(User.active.is_(True))):
        prefs={**DEFAULT,**user.preferences.get('notification_options',{})}
        if not prefs['enabled']:continue
        horizon=now+timedelta(hours=prefs['advance_hours'])
        # A version/deadline is notified once. Daily mode batches on the first server pass
        # of a local day; immediate mode checks every maintenance pass (five minutes).
        from .memory import MADRID
        day=now.astimezone(MADRID).date().isoformat()
        if prefs['frequency']=='daily' and user.preferences.get('reminder_day')==day:continue
        for event in events_for(db,user,start=now,end=horizon):
            if event['status']!='published' or event['starts_at']<=now.isoformat():continue
            category='exam' if event['kind']=='exam' else 'reminder'
            if prefs['priority']=='important' and category!='exam':continue
            notify(db,user.id,'Próximo evento: '+event['title'],'Consulta los detalles en tu calendario',category,f'upcoming:{event["id"]}:{event["version"]}:{user.id}')
        for task in assignments_for(db,user):
            from datetime import datetime
            due=datetime.fromisoformat(task['due_at'])
            if (now < due < horizon and task.get('class_status') != 'closed'
                and (not task.get('submission') or task['submission']['status'] not in
                     (('submitted', 'returned') if task.get('class_id') else ('submitted',)))):
                notify(db,user.id,'Entrega próxima: '+task['title'],'Consulta la tarea y prepara tu entrega','assignment',f'due:{task["id"]}:{user.id}')
        for task in db.scalars(select(PersonalTask).where(PersonalTask.user_id==user.id,PersonalTask.completed.is_(False),PersonalTask.due_at>now,PersonalTask.due_at<horizon)):
            notify(db,user.id,'Tarea personal próxima: '+task.title,'Revisa tus tareas personales','assignment',f'personal-due:{task.id}:{task.due_at.isoformat()}:{user.id}')
        for action in db.scalars(select(ActionRequest).where(ActionRequest.user_id==user.id,ActionRequest.status=='pending',ActionRequest.expires_at>now)):
            notify(db,user.id,'Propuesta pendiente de confirmar','Revisa los detalles de la propuesta en tu panel principal','action',f'approval:{action.id}')
        user.preferences={**user.preferences,'reminder_day':day}
