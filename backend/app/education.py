from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, Query, Request, UploadFile, File
from pydantic import AwareDatetime
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from .auth import get_db, current_user
from .db import utcnow
from .models import (Center, Course, Group, Subject, Classroom, AcademicYear, Teaching, User,
                     CalendarEvent, Exam, Assignment, Submission, Schedule, Enrollment,
                     Notification, BathroomPass, ActionRequest, LearnerProfile, LearnerSubject, PersonalTask)
from .policy import group_ids, event_filter, require_group, require_role, audit, get_event
from .schemas import SubmissionInput, BathroomArgs, PassCorrection
from .serializers import record

router = APIRouter(tags=['Plataforma académica'])


def events_for(db, user, kind=None, start=None, end=None):
    stmt = select(CalendarEvent).where(event_filter(db, user))
    if kind:
        stmt = stmt.where(CalendarEvent.kind == kind)
    if start:
        stmt = stmt.where(CalendarEvent.ends_at >= start)
    if end:
        stmt = stmt.where(CalendarEvent.starts_at < end)
    rows = list(db.scalars(stmt.order_by(CalendarEvent.starts_at).limit(500)))
    syllabi = dict(db.execute(select(Exam.event_id, Exam.syllabus).where(Exam.event_id.in_([r.id for r in rows]))).all())
    from .class_models import ClassEvent
    from .class_calendar import event_summary
    linked = {event_id: (class_id, activity_id) for event_id, class_id, activity_id in db.execute(
        select(ClassEvent.event_id, ClassEvent.class_id, ClassEvent.activity_id).where(ClassEvent.event_id.in_([row.id for row in rows]))
    )}
    return [event_summary(event, *linked[event.id]) if event.id in linked else
            dict(record(event), syllabus=syllabi.get(event.id, '')) for event in rows]


def assignments_for(db, user):
    rows = list(db.scalars(select(Assignment).where(Assignment.center_id == user.center_id, Assignment.group_id.in_(group_ids(db, user))).order_by(Assignment.due_at).limit(500)))
    submissions = {r.assignment_id: r for r in db.scalars(select(Submission).where(Submission.student_id == user.id))}
    legacy = [dict(record(a), submission=record(submissions[a.id]) if a.id in submissions else None) for a in rows]
    from .classwork import class_assignments
    return sorted([*legacy, *class_assignments(db, user)], key=lambda item: item['due_at'])


@router.get('/academic')
def metadata(user=Depends(current_user), db=Depends(get_db)):
    ids = group_ids(db, user)
    center = db.get(Center, user.center_id)
    subjects = select(Subject).where(Subject.center_id == user.center_id)
    teaching = select(Teaching).where(Teaching.group_id.in_(ids))
    if db.scalar(select(LearnerProfile.id).where(LearnerProfile.user_id==user.id)):
        subjects=subjects.where(Subject.id.in_(select(LearnerSubject.subject_id).where(LearnerSubject.user_id==user.id,LearnerSubject.active.is_(True))))
    elif user.role != 'admin':
        subjects = subjects.where(Subject.id.in_(select(Teaching.subject_id).where(Teaching.group_id.in_(ids))))
    teachers = select(User).where(User.id.in_(select(Teaching.teacher_id).where(Teaching.group_id.in_(ids))), User.center_id == user.center_id)
    return {'center': record(center), 'years': [record(x) for x in db.scalars(select(AcademicYear).where(AcademicYear.center_id == user.center_id))],
            'courses': [record(x) for x in db.scalars(select(Course).where(Course.center_id == user.center_id))],
            'groups': [record(x) for x in db.scalars(select(Group).where(Group.id.in_(ids)))],
            'subjects': [record(x) for x in db.scalars(subjects)],
            'classrooms': [record(x) for x in db.scalars(select(Classroom).where(Classroom.center_id == user.center_id))],
            'teaching': [record(x) for x in db.scalars(teaching)],
            'teachers': [{'id':x.id, 'display_name':x.display_name} for x in db.scalars(teachers)]}


@router.get('/events')
def events(kind: str | None = None, start: AwareDatetime | None = None, end: AwareDatetime | None = None,
           user=Depends(current_user), db=Depends(get_db)):
    return events_for(db, user, kind, start, end)


@router.get('/events/{event_id}')
def event_detail(event_id:str,user=Depends(current_user),db=Depends(get_db)):
    event=get_event(db,user,event_id)
    from .class_models import ClassEvent
    from .class_calendar import event_summary
    link = db.scalar(select(ClassEvent).where(ClassEvent.event_id == event.id))
    if link:
        return event_summary(event, link.class_id, link.activity_id)
    syllabus=db.scalar(select(Exam.syllabus).where(Exam.event_id==event.id))
    return record(event)|{'syllabus':syllabus or ''}


@router.get('/assignments')
def assignments(user=Depends(current_user), db=Depends(get_db)):
    return assignments_for(db, user)


@router.put('/assignments/{assignment_id}/submission')
def submit(assignment_id: str, body: SubmissionInput, user=Depends(current_user), db=Depends(get_db)):
    require_role(user, 'student')
    task = db.get(Assignment, assignment_id)
    if not task or task.center_id != user.center_id:
        raise HTTPException(404, 'Tarea no disponible')
    require_group(db, user, task.group_id)
    sub = db.scalar(select(Submission).where(Submission.assignment_id == task.id, Submission.student_id == user.id))
    if not sub:
        sub = Submission(assignment_id=task.id, student_id=user.id)
        db.add(sub)
    sub.content, sub.status = body.content, body.status
    db.commit()
    return record(sub)


@router.get('/assignments/{assignment_id}/submissions')
def submissions(assignment_id: str, user=Depends(current_user), db=Depends(get_db)):
    require_role(user, 'teacher', 'admin')
    task = db.get(Assignment, assignment_id)
    if not task or task.center_id != user.center_id:
        raise HTTPException(404, 'Tarea no disponible')
    require_group(db, user, task.group_id, task.subject_id, write=True)
    return [dict(record(s), student_name=u.display_name) for s, u in db.execute(select(Submission, User).join(User, User.id == Submission.student_id).where(Submission.assignment_id == task.id))]


@router.get('/schedules')
def schedules(user=Depends(current_user), db=Depends(get_db)):
    return [record(x) for x in db.scalars(select(Schedule).where(Schedule.center_id == user.center_id, Schedule.group_id.in_(group_ids(db, user))).order_by(Schedule.weekday, Schedule.starts))]


@router.get('/groups/{group_id}/students')
def students(group_id: str, user=Depends(current_user), db=Depends(get_db)):
    require_role(user, 'teacher', 'admin')
    require_group(db, user, group_id)
    return [{'id':u.id, 'display_name':u.display_name} for u in db.scalars(select(User).join(Enrollment).where(Enrollment.group_id == group_id, User.center_id == user.center_id, User.role == 'student', User.active.is_(True)))]


@router.get('/notifications')
def notifications(user=Depends(current_user), db=Depends(get_db)):
    return [record(n) for n in db.scalars(select(Notification).where(Notification.user_id == user.id).order_by(Notification.created_at.desc()).limit(150))]


@router.post('/notifications/read-all')
def read_all(user=Depends(current_user), db=Depends(get_db)):
    for n in db.scalars(select(Notification).where(Notification.user_id == user.id, Notification.read.is_(False))):
        n.read = True
    db.commit()
    return {'ok':True}


@router.patch('/notifications/{notification_id}/read')
def read(notification_id: str, user=Depends(current_user), db=Depends(get_db)):
    n = db.scalar(select(Notification).where(Notification.id == notification_id, Notification.user_id == user.id))
    if not n:
        raise HTTPException(404, 'Aviso no disponible')
    n.read = True
    db.commit()
    return record(n)


def notify(db, user_id, title, content, category, dedup_key=None):
    u = db.get(User, user_id)
    if not u or not u.active or u.preferences.get('notification_options',{}).get('enabled') is False or u.preferences.get('notifications', {}).get(category, True) is False:
        return
    if dedup_key and db.scalar(select(Notification.id).where(Notification.dedup_key == dedup_key)):
        return
    db.add(Notification(user_id=user_id, title=title[:180], content=content[:6000], category=category, dedup_key=dedup_key))


def notify_group(db, group_id, title, content, category):
    ids = set(db.scalars(select(Enrollment.user_id).where(Enrollment.group_id == group_id)))
    ids.update(db.scalars(select(Teaching.teacher_id).where(Teaching.group_id == group_id)))
    for uid in ids:
        notify(db, uid, title, content, category)


def bathroom_out(db, user, args):
    require_group(db, user, args.group_id, write=True)
    student = db.get(User, args.student_id)
    if not student or student.center_id != user.center_id or student.role != 'student' or not student.active or not db.scalar(select(Enrollment.id).where(Enrollment.user_id == student.id, Enrollment.group_id == args.group_id)):
        raise HTTPException(404, 'Alumno no disponible en este grupo')
    if db.scalar(select(BathroomPass.id).where(BathroomPass.student_id == student.id, BathroomPass.returned_at.is_(None))):
        raise HTTPException(409, 'Este alumno ya tiene una salida activa')
    p = BathroomPass(center_id=user.center_id, student_id=student.id, group_id=args.group_id, recorded_by=user.id)
    db.add(p)
    db.flush()
    audit(db, user, 'bathroom_out', p)
    return dict(record(p), student_name=student.display_name)


def bathroom_return(db, user, ident):
    p = db.get(BathroomPass, ident)
    if not p or p.center_id != user.center_id:
        raise HTTPException(404, 'Salida no disponible')
    require_group(db, user, p.group_id, write=True)
    if not p.returned_at:
        p.returned_at = utcnow()
        audit(db, user, 'bathroom_return', p)
    return record(p)


@router.get('/bathroom')
def passes(user=Depends(current_user), db=Depends(get_db)):
    require_role(user, 'teacher', 'admin')
    rows = db.execute(select(BathroomPass, User).join(User, User.id == BathroomPass.student_id).where(BathroomPass.center_id == user.center_id, BathroomPass.group_id.in_(group_ids(db, user))).order_by(BathroomPass.left_at.desc()).limit(150))
    return [dict(record(p), student_name=u.display_name) for p, u in rows]


@router.post('/bathroom', status_code=201)
def register_pass(body: BathroomArgs, user=Depends(current_user), db=Depends(get_db)):
    result = bathroom_out(db, user, body)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, 'Este alumno ya tiene una salida activa')
    return result


@router.post('/bathroom/{pass_id}/return')
def register_return(pass_id: str, user=Depends(current_user), db=Depends(get_db)):
    result = bathroom_return(db, user, pass_id)
    db.commit()
    return result


@router.patch('/bathroom/{pass_id}')
def correct(pass_id: str, body: PassCorrection, user=Depends(current_user), db=Depends(get_db)):
    p = db.get(BathroomPass, pass_id)
    if not p or p.center_id != user.center_id:
        raise HTTPException(404, 'Salida no disponible')
    require_group(db, user, p.group_id, write=True)
    if body.left_at > utcnow() or (body.returned_at and body.returned_at > utcnow()):
        raise HTTPException(422, 'El registro no puede estar en el futuro')
    p.left_at, p.returned_at, p.correction_reason = body.left_at, body.returned_at, body.reason
    audit(db, user, 'bathroom_corrected', p, {'reason':body.reason})
    db.commit()
    return record(p)


@router.get('/dashboard')
def dashboard(user=Depends(current_user), db=Depends(get_db)):
    now = utcnow()
    events = events_for(db, user, start=now, end=now + timedelta(days=90))
    tasks = assignments_for(db, user)
    from .knowledge import profile_for,personal_schedule
    from .memory import MADRID
    if profile_for(db,user):
        slots=personal_schedule(db,user,now.astimezone(MADRID).date().isoformat())['lessons'];today_count=sum(not s['is_break'] for s in slots)
    else:today_count=len(list(db.scalars(select(Schedule.id).where(Schedule.center_id==user.center_id,Schedule.group_id.in_(group_ids(db,user)),Schedule.weekday==now.astimezone(MADRID).weekday()))))
    return {'today_schedule_count':today_count,'personal_tasks':[record(t) for t in db.scalars(select(PersonalTask).where(PersonalTask.user_id==user.id,PersonalTask.completed.is_(False)).order_by(PersonalTask.due_at).limit(8))],'events': [e for e in events if e['status']=='published'][:8],
            'assignments': [a for a in tasks if a.get('class_status') != 'closed' and (not a['submission'] or a['submission']['status'] == 'draft')][:8],
            'pending_actions': [record(a) for a in db.scalars(select(ActionRequest).where(ActionRequest.user_id == user.id, ActionRequest.status=='pending', ActionRequest.expires_at > now))],
            'unread_notifications': len(list(db.scalars(select(Notification.id).where(Notification.user_id==user.id, Notification.read.is_(False)))))}


@router.post('/schedules/import')
async def import_schedule(request: Request, file: UploadFile=File(...), user=Depends(current_user),db=Depends(get_db)):
    import csv,io
    from .tools import run_tool
    require_role(user,'teacher','admin')
    raw=await file.read(1024*1024+1)
    await file.close()
    if len(raw)>1024*1024:raise HTTPException(413,'El CSV supera 1 MB')
    try:
        reader=csv.DictReader(io.StringIO(raw.decode('utf-8-sig')))
        if not {'group','subject','teacher','weekday','starts','ends'}.issubset(set(reader.fieldnames or [])):
            raise HTTPException(422,'Faltan columnas del CSV')
        entries=[]
        for row in reader:
            if len(entries)>=100:raise HTTPException(413,'Máximo 100 sesiones')
            group=db.scalar(select(Group).where(Group.center_id==user.center_id,Group.name==row['group'].strip()))
            subject=db.scalar(select(Subject).where(Subject.center_id==user.center_id,Subject.name==row['subject'].strip()))
            teacher=db.scalar(select(User).where(User.center_id==user.center_id,User.username==row['teacher'].strip()))
            room=db.scalar(select(Classroom).where(Classroom.center_id==user.center_id,Classroom.name==row.get('classroom','').strip())) if row.get('classroom') else None
            if not group or not subject or not teacher or (row.get('classroom') and not room):
                raise HTTPException(422,f'Fila {len(entries)+2}: grupo, asignatura, docente o aula no disponibles')
            entries.append({'group_id':group.id,'subject_id':subject.id,'teacher_id':teacher.id,'classroom_id':room.id if room else None,
                            'weekday':int(row['weekday']),'starts':row['starts'].strip(),'ends':row['ends'].strip()})
    except (UnicodeDecodeError,ValueError,KeyError,AttributeError,csv.Error):
        raise HTTPException(422,'CSV inválido. Usa UTF-8 y los nombres exactos de las columnas')
    result=run_tool(db,user,'import_schedule',{'entries':entries},request.app.state.settings)
    db.commit()
    return result
