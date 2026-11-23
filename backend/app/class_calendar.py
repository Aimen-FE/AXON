"""Class deadlines and meetings use the same events table as the general calendar."""
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select

from .auth import current_user, get_db
from .class_models import ClassEvent
from .class_policy import begin_class_write, class_by_id
from .class_schemas import ClassEventInput
from .models import CalendarEvent
from .policy import audit, event_filter
from .serializers import record

router = APIRouter(prefix='/classes', tags=['Calendario de clase'])


def event_summary(event, class_id, activity_id=None):
    return {**record(event), 'class_id': class_id, 'activity_id': activity_id, 'visibility': 'class', 'syllabus': ''}


def set_fields(event, values):
    for key, value in values.items():
        setattr(event, key, value)


def store_event(db, room, actor, values, *, purpose='event', activity_id=None, link=None):
    if not link:
        event = CalendarEvent(
            center_id=room.center_id, owner_id=actor.id, group_id=room.group_id, subject_id=room.subject_id,
            visibility='personal', source='Clases de AXON', **values,
        )
        db.add(event)
        db.flush()
        link = ClassEvent(class_id=room.id, event_id=event.id, purpose=purpose, activity_id=activity_id)
        db.add(link)
    else:
        event = db.get(CalendarEvent, link.event_id)
        set_fields(event, values)
        event.version += 1
    return event


def sync_activity_events(db, room, actor, activity):
    targets = {'deadline': {
        'title': activity.title, 'description': 'Fecha límite de entrega',
        'kind': 'assignment', 'starts_at': activity.due_at, 'ends_at': activity.due_at + timedelta(minutes=1),
    }}
    if activity.exam_at:
        targets['exam'] = {
            'title': activity.title, 'description': 'Examen programado de la clase',
            'kind': 'exam', 'starts_at': activity.exam_at,
            'ends_at': activity.exam_at + timedelta(minutes=activity.exam_minutes),
        }
    links = {link.purpose: link for link in db.scalars(select(ClassEvent).where(
        ClassEvent.class_id == room.id, ClassEvent.activity_id == activity.id,
    ))}
    for purpose, values in targets.items():
        store_event(db, room, actor, values, purpose=purpose, activity_id=activity.id, link=links.get(purpose))


def room_events(db, room, limit=300):
    return db.scalars(select(CalendarEvent).join(ClassEvent, ClassEvent.event_id == CalendarEvent.id)
                      .where(ClassEvent.class_id == room.id).order_by(CalendarEvent.starts_at).limit(limit))


def event_conflicts(db, user, starts_at, ends_at, exclude=None):
    return [event.title for event in db.scalars(select(CalendarEvent).where(
        event_filter(db, user), CalendarEvent.starts_at < ends_at, CalendarEvent.ends_at > starts_at,
        CalendarEvent.status == 'published', CalendarEvent.kind != 'assignment', CalendarEvent.id != exclude,
    ).order_by(CalendarEvent.starts_at).limit(12))]


@router.get('/{class_id}/calendar')
def calendar(class_id: str, user=Depends(current_user), db=Depends(get_db)):
    room = class_by_id(db, user, class_id)
    rows = db.execute(select(CalendarEvent, ClassEvent.activity_id).join(
        ClassEvent, ClassEvent.event_id == CalendarEvent.id,
    ).where(ClassEvent.class_id == room.id).order_by(CalendarEvent.starts_at).limit(300))
    return [event_summary(event, room.id, activity_id) for event, activity_id in rows]


@router.post('/{class_id}/calendar', status_code=201)
def add_event(class_id: str, body: ClassEventInput, user=Depends(current_user), db=Depends(get_db)):
    from .classes import notify_class
    begin_class_write(db, user)
    room = class_by_id(db, user, class_id, staff=True, write=True)
    conflicts = event_conflicts(db, user, body.starts_at, body.ends_at)
    event = store_event(db, room, user, body.model_dump())
    audit(db, user, 'class_event_published', event)
    notify_class(db, room, user, 'Nuevo evento en ' + room.name)
    db.commit()
    return {**event_summary(event, room.id), 'conflicts': conflicts}


@router.delete('/{class_id}/calendar/{event_id}')
def cancel_event(class_id: str, event_id: str, user=Depends(current_user), db=Depends(get_db)):
    begin_class_write(db, user)
    room = class_by_id(db, user, class_id, staff=True, write=True)
    link = db.scalar(select(ClassEvent).where(
        ClassEvent.class_id == room.id, ClassEvent.event_id == event_id, ClassEvent.activity_id.is_(None),
    ))
    if not link:
        raise HTTPException(404, 'Evento de clase no disponible')
    event = db.get(CalendarEvent, link.event_id)
    event.status = 'cancelled'
    event.version += 1
    audit(db, user, 'class_event_cancelled', event)
    db.commit()
    return event_summary(event, room.id)
