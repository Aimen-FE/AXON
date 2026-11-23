"""Activity publication, versioned submissions and human grade release."""
from datetime import timedelta

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from sqlalchemy import select

from .auth import current_user, get_db
from .class_calendar import sync_activity_events
from .class_files import active_quota, file_rows, file_summary
from .class_models import (
    ClassActivity, ClassFile, ClassGrade, ClassRubric, ClassSubmission, ClassSubmissionRevision,
    ClassTeam, ClassTeamMember, LearningClass,
)
from .class_policy import activity_access, begin_class_write, class_by_id, visible_classes
from .class_schemas import ActivityInput, ActivityState, ReturnInput, SubmissionInput
from .classes import active_members, notify_class, topic_for
from .db import utcnow
from .documents import document_download, persist_upload, prepare_upload
from .education import notify
from .models import User
from .operations import storage_lock
from .policy import audit, require_role
from .serializers import record

router = APIRouter(prefix='/classes', tags=['Actividades y entregas de clase'])


def activity_for(db, user, room, activity_id):
    activity = db.scalar(select(ClassActivity).where(
        ClassActivity.id == activity_id, ClassActivity.class_id == room.id, activity_access(user),
    ))
    if not activity:
        raise HTTPException(404, 'Actividad no disponible')
    return activity


def activity_locked(activity, user):
    return user.role == 'student' and activity.exam_at is not None and utcnow() < activity.exam_at


def rubric_for(db, activity):
    return db.scalar(select(ClassRubric).where(ClassRubric.activity_id == activity.id))


def team_for(db, user, class_id):
    return db.scalar(select(ClassTeam).join(ClassTeamMember, ClassTeamMember.team_id == ClassTeam.id).where(
        ClassTeam.class_id == class_id, ClassTeamMember.class_id == class_id, ClassTeamMember.student_id == user.id,
    ))


def my_submission(db, user, activity, *, must_have_team=False):
    if activity.delivery == 'team':
        team = team_for(db, user, activity.class_id)
        if not team:
            if must_have_team:
                raise HTTPException(409, 'El profesorado debe asignarte a un equipo')
            return None, None
        return db.scalar(select(ClassSubmission).where(ClassSubmission.activity_id == activity.id,
                                                       ClassSubmission.team_id == team.id)), team
    return db.scalar(select(ClassSubmission).where(ClassSubmission.activity_id == activity.id,
                                                   ClassSubmission.student_id == user.id)), None


def state_summary(submission):
    if not submission:
        return None
    return {'id': submission.id, 'status': submission.status, 'version': submission.version,
            'submitted_at': submission.submitted_at.isoformat() if submission.submitted_at else None}


def activity_detail(db, user, activity):
    locked = activity_locked(activity, user)
    result = {**record(activity), 'locked': locked}
    if locked:
        return {**result, 'instructions': '', 'questions': [], 'rubric': [], 'files': []}
    rubric = rubric_for(db, activity)
    rows = file_rows(db, ClassFile.class_id == activity.class_id, ClassFile.activity_id == activity.id,
                     ClassFile.hidden.is_(False))
    return {**result, 'rubric': rubric.criteria if rubric else [],
            'files': [file_summary(link, doc) for link, doc in rows]}


def write_activity(db, room, activity, body):
    topic_for(db, room, body.topic_id)
    for key, value in body.model_dump(exclude={'rubric'}).items():
        setattr(activity, key, value)
    db.add(activity)
    db.flush()
    rubric = rubric_for(db, activity)
    if body.rubric:
        if rubric is None:
            rubric = ClassRubric(activity_id=activity.id)
            db.add(rubric)
        rubric.criteria = [item.model_dump() for item in body.rubric]
    elif rubric:
        db.delete(rubric)


@router.get('/{class_id}/activities')
def activities(class_id: str, user=Depends(current_user), db=Depends(get_db)):
    room = class_by_id(db, user, class_id)
    rows = db.scalars(select(ClassActivity).where(ClassActivity.class_id == room.id, activity_access(user))
                     .order_by(ClassActivity.due_at.is_(None), ClassActivity.due_at, ClassActivity.created_at.desc())
                     .limit(300))
    result = []
    for activity in rows:
        item = {**record(activity, ('instructions', 'questions')), 'locked': activity_locked(activity, user)}
        if user.role == 'student':
            submission, _ = my_submission(db, user, activity)
            item['submission'] = state_summary(submission)
        result.append(item)
    return result


@router.post('/{class_id}/activities', status_code=201)
def create_activity(class_id: str, body: ActivityInput, user=Depends(current_user), db=Depends(get_db)):
    begin_class_write(db, user)
    room = class_by_id(db, user, class_id, staff=True, write=True)
    activity = ClassActivity(class_id=room.id, creator_id=user.id, status='draft')
    write_activity(db, room, activity, body)
    audit(db, user, 'class_activity_drafted', activity)
    db.commit()
    return activity_detail(db, user, activity)


@router.get('/{class_id}/activities/{activity_id}')
def get_activity(class_id: str, activity_id: str, user=Depends(current_user), db=Depends(get_db)):
    room = class_by_id(db, user, class_id)
    return activity_detail(db, user, activity_for(db, user, room, activity_id))


@router.put('/{class_id}/activities/{activity_id}')
def edit_activity(class_id: str, activity_id: str, body: ActivityInput, user=Depends(current_user), db=Depends(get_db)):
    begin_class_write(db, user)
    room = class_by_id(db, user, class_id, staff=True, write=True)
    activity = activity_for(db, user, room, activity_id)
    if activity.status != 'draft':
        raise HTTPException(409, 'La edición completa solo está disponible en borradores')
    write_activity(db, room, activity, body)
    audit(db, user, 'class_activity_edited', activity)
    db.commit()
    return activity_detail(db, user, activity)


@router.put('/{class_id}/activities/{activity_id}/state')
def set_activity_state(
    class_id: str, activity_id: str, body: ActivityState, user=Depends(current_user), db=Depends(get_db),
):
    begin_class_write(db, user)
    room = class_by_id(db, user, class_id, staff=True, write=True)
    activity = activity_for(db, user, room, activity_id)
    if activity.status == body.status:
        return activity_detail(db, user, activity)
    if body.status == 'closed' and activity.status == 'draft':
        raise HTTPException(409, 'Publica primero la actividad')
    if body.status == 'published':
        if not activity.due_at or activity.due_at <= utcnow():
            raise HTTPException(422, 'Indica una fecha de entrega futura')
        if activity.kind == 'exam' and (not activity.exam_at or
            activity.due_at < activity.exam_at + timedelta(minutes=activity.exam_minutes)):
            raise HTTPException(422, 'Programa el examen y fija la entrega después de su finalización')
        if activity.kind == 'quiz' and not activity.questions:
            raise HTTPException(422, 'Incluye al menos una pregunta')
        if activity.delivery == 'team' and not db.scalar(select(ClassTeam.id).where(
            ClassTeam.class_id == room.id,
        ).limit(1)):
            raise HTTPException(422, 'Crea al menos un equipo en Personas')
        sync_activity_events(db, room, user, activity)
        if activity.status == 'draft':
            notify_class(db, room, user, 'Actividad publicada en ' + room.name, 'assignment')
    activity.status = body.status
    audit(db, user, 'class_activity_' + body.status, activity)
    db.commit()
    return activity_detail(db, user, activity)


def grade_summary(grade):
    return record(grade) if grade else None


def active_submission_files(db, submission):
    return [file_summary(link, doc) for link, doc in file_rows(
        db, ClassFile.submission_id == submission.id, ClassFile.hidden.is_(False),
    )]


def submission_payload(db, submission):
    grade = db.scalar(select(ClassGrade).where(ClassGrade.submission_id == submission.id))
    return {**record(submission), 'grade': grade_summary(grade), 'files': active_submission_files(db, submission)}


def save_revision(db, user, submission, change):
    submission.version += 1
    payload = submission_payload(db, submission)
    db.add(ClassSubmissionRevision(
        submission_id=submission.id, author_id=user.id, version=submission.version, change=change,
        snapshot={key: payload[key] for key in ('content', 'answers', 'status', 'submitted_at', 'files', 'grade')},
    ))
    return payload


def ensure_submission_open(room, activity, user):
    if room.archived or activity.status != 'published':
        raise HTTPException(409, 'La actividad no admite entregas')
    if activity_locked(activity, user):
        raise HTTPException(409, 'El examen todavía no ha comenzado')
    if not activity.due_at or utcnow() > activity.due_at:
        raise HTTPException(409, 'El plazo de entrega ha terminado')


def ensure_draft(db, user, activity, version):
    submission, team = my_submission(db, user, activity, must_have_team=True)
    if version != (submission.version if submission else 0):
        raise HTTPException(409, 'La entrega ha cambiado. Vuelve a abrirla para cargar la última versión')
    if submission and submission.status == 'submitted':
        raise HTTPException(409, 'La entrega está enviada y pendiente de corrección')
    if not submission:
        submission = ClassSubmission(activity_id=activity.id, team_id=team.id if team else None,
                                     student_id=None if team else user.id)
        db.add(submission)
        db.flush()
    submission.status = 'draft'
    return submission


@router.get('/{class_id}/activities/{activity_id}/submission')
def get_submission(class_id: str, activity_id: str, user=Depends(current_user), db=Depends(get_db)):
    require_role(user, 'student')
    room = class_by_id(db, user, class_id)
    activity = activity_for(db, user, room, activity_id)
    submission, _ = my_submission(db, user, activity)
    return submission_payload(db, submission) if submission else None


@router.put('/{class_id}/activities/{activity_id}/submission')
def save_submission(
    class_id: str, activity_id: str, body: SubmissionInput, user=Depends(current_user), db=Depends(get_db),
):
    begin_class_write(db, user)
    require_role(user, 'student')
    room = class_by_id(db, user, class_id, write=True)
    activity = activity_for(db, user, room, activity_id)
    ensure_submission_open(room, activity, user)
    submission = ensure_draft(db, user, activity, body.version)
    if len(body.answers) > len(activity.questions):
        raise HTTPException(422, 'Hay más respuestas que preguntas')
    for question, answer in zip(activity.questions, body.answers):
        if answer and question['options'] and answer not in question['options']:
            raise HTTPException(422, 'Selecciona una opción válida')
    submission.content, submission.answers = body.content, body.answers
    change = 'draft'
    if body.submit:
        if activity.questions and (len(body.answers) != len(activity.questions) or not all(body.answers)):
            raise HTTPException(422, 'Responde a todas las preguntas antes de entregar')
        if not body.content and not any(body.answers) and not active_submission_files(db, submission):
            raise HTTPException(422, 'Escribe una respuesta o añade un archivo')
        submission.status, submission.submitted_at = 'submitted', utcnow()
        change = 'submitted'
        for teacher in active_members(db, room, 'teacher'):
            notify(db, teacher.id, 'Nueva entrega de ' + activity.title, 'Revísala desde Actividades.', 'assignment')
        audit(db, user, 'class_submission_sent', submission)
    result = save_revision(db, user, submission, change)
    db.commit()
    return result


@router.post('/{class_id}/activities/{activity_id}/submission/files', status_code=201)
async def add_attachment(
    class_id: str, activity_id: str, request: Request, file: UploadFile = File(...),
    version: int = Form(..., ge=0), user=Depends(current_user), db=Depends(get_db),
):
    require_role(user, 'student')
    room = class_by_id(db, user, class_id)
    ensure_submission_open(room, activity_for(db, user, room, activity_id), user)
    prepared = await prepare_upload(request, file, class_file=True, index=False)
    settings = request.app.state.settings
    with storage_lock(settings):
        begin_class_write(db, user)
        require_role(user, 'student')
        room = class_by_id(db, user, class_id, write=True)
        activity = activity_for(db, user, room, activity_id)
        ensure_submission_open(room, activity, user)
        submission = ensure_draft(db, user, activity, version)
        if len(active_submission_files(db, submission)) >= 5:
            raise HTTPException(409, 'Cada entrega admite hasta cinco archivos activos')
        active_quota(db, room, request, user, prepared)
        with persist_upload(settings, db, user, prepared, title=prepared.filename[:180], access='personal',
                            source='Adjunto de entrega') as document:
            db.add(ClassFile(class_id=room.id, document_id=document.id, submission_id=submission.id))
            db.flush()
            result = save_revision(db, user, submission, 'file_added')
            db.commit()
    return result


@router.delete('/{class_id}/activities/{activity_id}/submission/files/{document_id}')
def remove_attachment(
    class_id: str, activity_id: str, document_id: str, version: int,
    user=Depends(current_user), db=Depends(get_db),
):
    begin_class_write(db, user)
    require_role(user, 'student')
    room = class_by_id(db, user, class_id, write=True)
    activity = activity_for(db, user, room, activity_id)
    ensure_submission_open(room, activity, user)
    submission = ensure_draft(db, user, activity, version)
    link = db.scalar(select(ClassFile).where(ClassFile.class_id == room.id, ClassFile.document_id == document_id,
                                             ClassFile.submission_id == submission.id, ClassFile.hidden.is_(False)))
    if not link:
        raise HTTPException(404, 'Archivo no disponible')
    link.hidden = True
    result = save_revision(db, user, submission, 'file_removed')
    db.commit()
    return result


def submission_label(db, submission):
    if submission.team_id:
        return db.get(ClassTeam, submission.team_id).name
    return db.get(User, submission.student_id).display_name


@router.get('/{class_id}/activities/{activity_id}/submissions')
def review_queue(class_id: str, activity_id: str, user=Depends(current_user), db=Depends(get_db)):
    room = class_by_id(db, user, class_id, staff=True)
    activity = activity_for(db, user, room, activity_id)
    rows = db.scalars(select(ClassSubmission).where(
        ClassSubmission.activity_id == activity.id, ClassSubmission.status != 'draft',
    ).order_by(ClassSubmission.submitted_at.desc()).limit(300))
    return [{**submission_payload(db, submission), 'author_name': submission_label(db, submission)} for submission in rows]


def readable_submission(db, room, user, activity_id, submission_id):
    activity = activity_for(db, user, room, activity_id)
    submission = db.scalar(select(ClassSubmission).where(
        ClassSubmission.id == submission_id, ClassSubmission.activity_id == activity.id,
    ))
    if user.role == 'student':
        own, _ = my_submission(db, user, activity)
        if not own or own.id != submission_id:
            raise HTTPException(404, 'Entrega no disponible')
    if not submission:
        raise HTTPException(404, 'Entrega no disponible')
    return activity, submission


@router.get('/{class_id}/activities/{activity_id}/submissions/{submission_id}/history')
def history(
    class_id: str, activity_id: str, submission_id: str, user=Depends(current_user), db=Depends(get_db),
):
    room = class_by_id(db, user, class_id)
    _, submission = readable_submission(db, room, user, activity_id, submission_id)
    query = select(ClassSubmissionRevision).where(ClassSubmissionRevision.submission_id == submission.id)
    if user.role != 'student':
        query = query.where(ClassSubmissionRevision.change.in_(('submitted', 'returned')))
    rows = [record(revision) for revision in db.scalars(query.order_by(ClassSubmissionRevision.version.desc()).limit(80))]
    if user.role != 'student' and not rows:
        raise HTTPException(404, 'Entrega no disponible')
    return rows


@router.get('/{class_id}/activities/{activity_id}/submissions/{submission_id}/files/{document_id}')
def download_attachment(
    class_id: str, activity_id: str, submission_id: str, document_id: str, request: Request,
    user=Depends(current_user), db=Depends(get_db),
):
    room = class_by_id(db, user, class_id)
    _, submission = readable_submission(db, room, user, activity_id, submission_id)
    row = file_rows(db, ClassFile.class_id == room.id, ClassFile.submission_id == submission.id,
                    ClassFile.document_id == document_id).first()
    if not row:
        raise HTTPException(404, 'Archivo no disponible')
    if user.role != 'student':
        revisions = db.scalars(select(ClassSubmissionRevision).where(
            ClassSubmissionRevision.submission_id == submission.id,
            ClassSubmissionRevision.change.in_(('submitted', 'returned')),
        ))
        if not any(item['id'] == document_id for revision in revisions for item in revision.snapshot['files']):
            raise HTTPException(404, 'Archivo no disponible')
    return document_download(db, row[1], request.app.state.settings)


@router.post('/{class_id}/activities/{activity_id}/submissions/{submission_id}/return')
def return_submission(
    class_id: str, activity_id: str, submission_id: str, body: ReturnInput,
    user=Depends(current_user), db=Depends(get_db),
):
    begin_class_write(db, user)
    room = class_by_id(db, user, class_id, staff=True, write=True)
    activity, submission = readable_submission(db, room, user, activity_id, submission_id)
    if submission.status not in ('submitted','returned') or submission.version != body.version:
        raise HTTPException(409, 'La entrega ya se ha corregido o ha cambiado')
    rubric = rubric_for(db, activity)
    if rubric:
        if (len(body.criteria_scores) != len(rubric.criteria) or
            any(score > criterion['points'] for score, criterion in zip(body.criteria_scores, rubric.criteria)) or
            (body.points is not None and body.points != sum(body.criteria_scores))):
            raise HTTPException(422, 'La evaluación debe seguir la rúbrica publicada')
        points = sum(body.criteria_scores)
    else:
        if body.criteria_scores or (body.points is not None and (
            activity.max_points is None or body.points > activity.max_points
        )):
            raise HTTPException(422, 'La puntuación supera la escala de la actividad')
        points = body.points
    grade = db.scalar(select(ClassGrade).where(ClassGrade.submission_id == submission.id))
    if not grade:
        grade = ClassGrade(submission_id=submission.id)
        db.add(grade)
    grade.reviewer_id, grade.points, grade.feedback = user.id, points, body.feedback
    grade.criteria_scores = body.criteria_scores
    submission.status = 'returned'
    recipients = ({submission.student_id} if submission.student_id else set(db.scalars(
        select(ClassTeamMember.student_id).where(ClassTeamMember.team_id == submission.team_id),
    )))
    for member in active_members(db, room, 'student'):
        if member.id in recipients:
            notify(db, member.id, 'Corrección disponible de ' + activity.title,
                   'Consulta tu entrega y los comentarios en Clases.', 'class')
    audit(db, user, 'class_submission_returned_by_staff', submission)
    result = save_revision(db, user, submission, 'returned')
    db.commit()
    return result


@router.get('/{class_id}/grades')
def grades(class_id: str, user=Depends(current_user), db=Depends(get_db)):
    room = class_by_id(db, user, class_id)
    query = select(ClassGrade, ClassSubmission, ClassActivity).join(
        ClassSubmission, ClassGrade.submission_id == ClassSubmission.id,
    ).join(ClassActivity, ClassSubmission.activity_id == ClassActivity.id).where(ClassActivity.class_id == room.id)
    if user.role == 'student':
        team = team_for(db, user, room.id)
        query = query.where((ClassSubmission.student_id == user.id) |
                            (ClassSubmission.team_id == team.id if team else False))
    return [
        {**grade_summary(grade), 'activity_id': activity.id, 'title': activity.title, 'max_points': activity.max_points,
         'status': submission.status, 'author_name': submission_label(db, submission)}
        for grade, submission, activity in db.execute(query.order_by(ClassGrade.updated_at.desc()).limit(300))
    ]


def class_assignments(db, user):
    """Project published class work into the existing tasks surface and reminders."""
    rows = db.execute(select(ClassActivity, LearningClass).join(
        LearningClass, LearningClass.id == ClassActivity.class_id,
    ).where(
        LearningClass.id.in_(visible_classes(user)), LearningClass.archived.is_(False),
        ClassActivity.status.in_(('published', 'closed')), ClassActivity.due_at.is_not(None),
    ).order_by(ClassActivity.due_at).limit(500))
    results = []
    for activity, room in rows:
        submission, _ = my_submission(db, user, activity) if user.role == 'student' else (None, None)
        results.append({
            'id': activity.id, 'class_id': room.id, 'center_id': room.center_id, 'group_id': room.group_id,
            'subject_id': room.subject_id, 'creator_id': activity.creator_id, 'title': activity.title,
            'description': '' if activity_locked(activity, user) else activity.instructions,
            'due_at': activity.due_at.isoformat(), 'created_at': activity.created_at.isoformat(),
            'updated_at': activity.updated_at.isoformat(), 'material_ids': [],
            'submission': state_summary(submission), 'class_status': activity.status,
        })
    return results
