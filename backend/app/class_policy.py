"""Server-side boundaries for native classes and their shared resources."""
from fastapi import HTTPException
from sqlalchemy import or_, select, text

from .db import utcnow
from .class_models import ClassActivity, ClassEvent, ClassFile, ClassMember, LearningClass


def visible_classes(user):
    result = select(LearningClass.id).where(LearningClass.center_id == user.center_id)
    if user.role != 'admin':
        result = result.where(select(ClassMember.id).where(
            ClassMember.class_id == LearningClass.id,
            ClassMember.user_id == user.id,
            ClassMember.role == user.role,
            ClassMember.active.is_(True),
        ).correlate(LearningClass).exists())
    return result


def class_by_id(db, user, class_id, *, staff=False, write=False, allow_archived=False):
    if staff and user.role not in ('teacher', 'admin'):
        raise HTTPException(403, 'Solo el equipo docente puede realizar esta operación')
    query = select(LearningClass).where(LearningClass.id == class_id, LearningClass.id.in_(visible_classes(user)))
    if write:
        query = query.with_for_update()
    room = db.scalar(query)
    if not room:
        raise HTTPException(404, 'Clase no disponible')
    if write and room.archived and not allow_archived:
        raise HTTPException(409, 'La clase está archivada')
    return room


def begin_class_write(db, user):
    if db.bind.dialect.name == 'sqlite':
        db.execute(text('BEGIN IMMEDIATE'))
    db.refresh(user, with_for_update=True)
    if not user.active:
        raise HTTPException(403, 'La cuenta ya no tiene acceso')


def activity_access(user):
    if user.role == 'student':
        return ClassActivity.status.in_(('published', 'closed'))
    return ClassActivity.status.in_(('draft', 'published', 'closed'))


def class_event_ids(user):
    return select(ClassEvent.event_id).where(ClassEvent.class_id.in_(visible_classes(user)))


def class_document_ids(user, class_id=None):
    """The general document index never includes submission attachments."""
    allowed = select(ClassFile.document_id).where(
        ClassFile.class_id.in_(visible_classes(user)),
        ClassFile.hidden.is_(False),
        ClassFile.submission_id.is_(None),
    )
    if class_id is not None:
        allowed = allowed.where(ClassFile.class_id == class_id)
    activity = select(ClassActivity.id).where(
        ClassActivity.id == ClassFile.activity_id, ClassActivity.class_id == ClassFile.class_id, activity_access(user),
    ).correlate(ClassFile)
    if user.role == 'student':
        activity = activity.where(or_(ClassActivity.exam_at.is_(None), ClassActivity.exam_at <= utcnow()))
    return allowed.where(or_(ClassFile.activity_id.is_(None), activity.exists()))
