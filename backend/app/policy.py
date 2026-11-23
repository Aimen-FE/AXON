from fastapi import HTTPException
from sqlalchemy import select, or_, and_
from .class_models import ClassEvent, ClassFile
from .class_policy import class_event_ids, class_document_ids
from .models import Group, Subject, Classroom, Enrollment, Teaching, CalendarEvent, Document, AuditLog


def group_ids(db, user):
    if user.role == 'admin':
        return list(db.scalars(select(Group.id).where(Group.center_id == user.center_id)))
    if user.role == 'teacher':
        return list(db.scalars(select(Teaching.group_id).join(Group).where(Teaching.teacher_id == user.id, Group.center_id == user.center_id).distinct()))
    return list(db.scalars(select(Enrollment.group_id).join(Group).where(Enrollment.user_id == user.id, Group.center_id == user.center_id)))


def require_role(user, *roles):
    if user.role not in roles:
        raise HTTPException(403, 'Tu perfil no permite esta operación')


def require_group(db, user, group_id, subject_id=None, write=False):
    group = db.get(Group, group_id)
    if not group or group.center_id != user.center_id or group_id not in group_ids(db, user):
        raise HTTPException(404, 'Grupo no disponible')
    if write:
        require_role(user, 'teacher', 'admin')
    if subject_id:
        subject = db.get(Subject, subject_id)
        if not subject or subject.center_id != user.center_id:
            raise HTTPException(404, 'Asignatura no disponible')
        if user.role == 'teacher' and not db.scalar(select(Teaching.id).where(Teaching.teacher_id == user.id, Teaching.group_id == group_id, Teaching.subject_id == subject_id)):
            raise HTTPException(403, 'No tienes esta asignatura asignada en el grupo')
        if user.role == 'student' and not db.scalar(select(Teaching.id).where(Teaching.group_id == group_id, Teaching.subject_id == subject_id)):
            raise HTTPException(404, 'Asignatura no disponible en el grupo')
    return group


def check_classroom(db, user, classroom_id):
    if classroom_id:
        room = db.get(Classroom, classroom_id)
        if not room or room.center_id != user.center_id:
            raise HTTPException(404, 'Aula no disponible')


def event_filter(db, user):
    legacy_scope = or_(
        and_(CalendarEvent.visibility == 'personal', CalendarEvent.owner_id == user.id),
        CalendarEvent.visibility == 'center',
        and_(CalendarEvent.visibility == 'group', CalendarEvent.group_id.in_(group_ids(db, user))),
    )
    return and_(CalendarEvent.center_id == user.center_id, or_(
        and_(CalendarEvent.id.not_in(select(ClassEvent.event_id)), legacy_scope),
        CalendarEvent.id.in_(class_event_ids(user)),
    ))


def document_filter(db, user):
    legacy_scope = or_(
        Document.owner_id == user.id,
        and_(Document.access.in_(['center', 'public']), Document.status.in_(['validated', 'official'])),
        and_(Document.access == 'group', Document.group_id.in_(group_ids(db, user))),
    )
    return and_(Document.center_id == user.center_id, or_(
        and_(Document.id.not_in(select(ClassFile.document_id)), legacy_scope),
        Document.id.in_(class_document_ids(user)),
    ))


def get_document(db, user, ident):
    obj = db.scalar(select(Document).where(Document.id == ident, document_filter(db, user)))
    if not obj:
        raise HTTPException(404, 'Documento no disponible')
    return obj


def get_event(db, user, ident, write=False):
    obj = db.scalar(select(CalendarEvent).where(CalendarEvent.id == ident, event_filter(db, user)))
    if not obj:
        raise HTTPException(404, 'Evento no disponible')
    if write and db.scalar(select(ClassEvent.id).where(ClassEvent.event_id == obj.id)):
        raise HTTPException(409, 'Gestiona este evento desde Clases')
    if write and obj.visibility == 'personal':
        if obj.owner_id != user.id:
            raise HTTPException(404, 'Evento no disponible')
    elif write and obj.visibility == 'group':
        require_group(db, user, obj.group_id, obj.subject_id, write=True)
    elif write:
        require_role(user, 'admin')
    return obj


def audit(db, user, operation, obj, details=None):
    db.add(AuditLog(center_id=user.center_id, actor_id=user.id, operation=operation,
                    object_type=obj.__tablename__, object_id=obj.id, details=details or {}))
