"""Shared document storage with class, activity and submission boundaries."""
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from sqlalchemy import func, select

from .auth import current_user, get_db
from .class_models import ClassActivity, ClassFile
from .class_policy import begin_class_write, class_by_id, class_document_ids
from .classes import topic_for
from .documents import document_download, persist_upload, prepare_upload
from .models import Document
from .operations import storage_lock
from .policy import audit
from .serializers import record

router = APIRouter(prefix='/classes', tags=['Documentos de clase'])
CLASS_STORAGE_LIMIT = 250 * 1024 * 1024


def active_quota(db, room, request, user, prepared):
    used = db.scalar(select(func.coalesce(func.sum(Document.size), 0)).join(ClassFile, ClassFile.document_id == Document.id)
                     .where(ClassFile.class_id == room.id))
    if used + len(prepared.raw) > CLASS_STORAGE_LIMIT:
        raise HTTPException(413, 'La clase ha alcanzado su límite de almacenamiento')
    if request.app.state.settings.full_demo:
        from .teacher_demo import upload_limit
        upload_limit(db, user, len(prepared.raw))


def file_summary(link, document):
    return {
        'id': document.id,
        'title': document.title,
        'filename': document.filename,
        'size': document.size,
        'topic_id': link.topic_id,
        'activity_id': link.activity_id,
        'created_at': link.created_at.isoformat(),
    }


def file_rows(db, *conditions):
    return db.execute(select(ClassFile, Document).join(Document, Document.id == ClassFile.document_id)
                      .where(*conditions).order_by(ClassFile.created_at.desc()))


@router.get('/{class_id}/files')
def files(class_id: str, user=Depends(current_user), db=Depends(get_db)):
    room = class_by_id(db, user, class_id)
    rows = file_rows(db, ClassFile.class_id == room.id, ClassFile.activity_id.is_(None),
                     ClassFile.document_id.in_(class_document_ids(user, room.id)))
    return [file_summary(link, document) for link, document in rows.fetchmany(300)]


@router.post('/{class_id}/files', status_code=201)
async def add_file(
    class_id: str, request: Request, file: UploadFile = File(...), title: str = Form(..., max_length=180),
    topic_id: str | None = Form(None, max_length=36), activity_id: str | None = Form(None, max_length=36),
    user=Depends(current_user), db=Depends(get_db),
):
    class_by_id(db, user, class_id, staff=True)
    if not title.strip() or (topic_id and activity_id):
        raise HTTPException(422, 'Indica un título y un destino válido')
    prepared = await prepare_upload(request, file, class_file=True)
    settings = request.app.state.settings
    with storage_lock(settings):
        begin_class_write(db, user)
        room = class_by_id(db, user, class_id, staff=True, write=True)
        topic = topic_for(db, room, topic_id)
        if activity_id and not db.scalar(select(ClassActivity.id).where(
            ClassActivity.id == activity_id, ClassActivity.class_id == room.id,
        )):
            raise HTTPException(404, 'Actividad no disponible')
        active_quota(db, room, request, user, prepared)
        with persist_upload(settings, db, user, prepared, title=title.strip(), access='personal',
                            source='Material de clase', subject_id=room.subject_id) as document:
            link = ClassFile(class_id=room.id, document_id=document.id, topic_id=topic.id if topic else None,
                             activity_id=activity_id)
            db.add(link)
            db.flush()
            audit(db, user, 'class_file_added', link)
            db.commit()
    return file_summary(link, document)


@router.delete('/{class_id}/files/{document_id}')
def hide_file(class_id: str, document_id: str, user=Depends(current_user), db=Depends(get_db)):
    begin_class_write(db, user)
    room = class_by_id(db, user, class_id, staff=True, write=True)
    link = db.scalar(select(ClassFile).where(ClassFile.class_id == room.id, ClassFile.document_id == document_id,
                                             ClassFile.submission_id.is_(None), ClassFile.hidden.is_(False)))
    if not link:
        raise HTTPException(404, 'Archivo no disponible')
    link.hidden = True
    audit(db, user, 'class_file_hidden', link)
    db.commit()
    return {'ok': True}
