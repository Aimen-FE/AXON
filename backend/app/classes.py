"""Class roster, invitations, discussion and organization."""
from datetime import timedelta
from secrets import token_urlsafe

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select

from .auth import current_user, digest, get_db
from .class_models import (
    ClassComment, ClassInvitation, ClassMember, ClassPost, ClassTeam, ClassTeamMember, ClassTopic, LearningClass,
)
from .class_policy import begin_class_write, class_by_id, visible_classes
from .class_schemas import (
    ArchiveInput, ClassCreate, ClassInput, CommentInput, JoinInput, MemberInput, PostInput, TeamInput, TopicInput,
)
from .db import utcnow
from .education import notify
from .models import Course, Group, Subject, User
from .policy import audit, require_group, require_role
from .serializers import record

router = APIRouter(prefix='/classes', tags=['Clases nativas'])


def class_summary(db, user, room):
    group = db.get(Group, room.group_id)
    return {
        **record(room, ('join_hash',)),
        'group': group.name,
        'stage': db.get(Course, group.course_id).stage,
        'course_id': group.course_id,
        'course': db.get(Course, group.course_id).name,
        'subject': db.get(Subject, room.subject_id).name,
        'can_manage': user.role in ('teacher', 'admin'),
        'has_join_code': bool(room.join_hash) if user.role in ('teacher', 'admin') else False,
    }


def member_record(db, room, user_id):
    return db.scalar(select(ClassMember).where(ClassMember.class_id == room.id, ClassMember.user_id == user_id))


def active_members(db, room, role=None):
    query = select(User).join(ClassMember, ClassMember.user_id == User.id).where(
        ClassMember.class_id == room.id, ClassMember.active.is_(True),
        User.active.is_(True), User.role == ClassMember.role, User.center_id == room.center_id,
    )
    if role:
        query = query.where(ClassMember.role == role)
    return db.scalars(query.order_by(User.display_name))


def notify_class(db, room, actor, title, category='class'):
    for member in active_members(db, room):
        if member.id != actor.id:
            notify(db, member.id, title, 'Abre Clases para consultar los detalles.', category)


def topic_for(db, room, topic_id):
    if not topic_id:
        return None
    topic = db.scalar(select(ClassTopic).where(ClassTopic.id == topic_id, ClassTopic.class_id == room.id))
    if not topic:
        raise HTTPException(404, 'Tema no disponible')
    return topic


@router.get('')
def list_classes(user=Depends(current_user), db=Depends(get_db)):
    rows = db.scalars(select(LearningClass).where(LearningClass.id.in_(visible_classes(user)))
                     .order_by(LearningClass.archived, LearningClass.name).limit(300))
    invitations = []
    if user.role == 'student':
        invitations = [
            {'id': room.id, 'name': room.name, 'subject': subject, 'expires_at': deadline.isoformat()}
            for room, subject, deadline in db.execute(select(LearningClass, Subject.name, ClassInvitation.expires_at)
                .join(ClassInvitation, ClassInvitation.class_id == LearningClass.id)
                .join(Subject, Subject.id == LearningClass.subject_id)
                .where(ClassInvitation.user_id == user.id, ClassInvitation.expires_at > utcnow(),
                       LearningClass.center_id == user.center_id, LearningClass.archived.is_(False))
                .order_by(ClassInvitation.expires_at).limit(150))
        ]
    return {'classes': [class_summary(db, user, room) for room in rows], 'invitations': invitations}


@router.post('', status_code=201)
def create_class(body: ClassCreate, user=Depends(current_user), db=Depends(get_db)):
    begin_class_write(db, user)
    require_role(user, 'teacher', 'admin')
    require_group(db, user, body.group_id, body.subject_id, write=True)
    code = token_urlsafe(18)
    room = LearningClass(center_id=user.center_id, creator_id=user.id, join_hash=digest(code), **body.model_dump())
    db.add(room)
    db.flush()
    if user.role == 'teacher':
        db.add(ClassMember(class_id=room.id, user_id=user.id, role='teacher'))
    from .education_settings import admission_for
    admission_for(db, room)
    audit(db, user, 'class_created', room)
    db.commit()
    return {**class_summary(db, user, room), 'join_code': code}


@router.post('/join')
def join_by_code(body: JoinInput, user=Depends(current_user), db=Depends(get_db)):
    begin_class_write(db, user)
    require_role(user, 'student')
    room = db.scalar(select(LearningClass).where(
        LearningClass.center_id == user.center_id, LearningClass.join_hash == digest(body.code),
        LearningClass.archived.is_(False),
    ).with_for_update())
    if not room:
        raise HTTPException(404, 'El código no da acceso a una clase disponible')
    from .education_settings import admission_for
    admission = admission_for(db, room)
    if not admission.code_expires_at or admission.code_expires_at <= utcnow() or admission.code_uses >= admission.code_limit:
        raise HTTPException(404, 'El código ha caducado o agotado sus usos')
    member = member_record(db, room, user.id)
    if member and (not member.active or member.role != 'student'):
        raise HTTPException(404, 'Pide al profesorado una nueva invitación')
    if member and member.active:
        return class_summary(db, user, room)
    from .nebula_models import ClassJoinRequest
    if admission.review_codes:
        pending = db.scalar(select(ClassJoinRequest).where(ClassJoinRequest.class_id==room.id,ClassJoinRequest.user_id==user.id))
        if not pending:
            pending=ClassJoinRequest(class_id=room.id,user_id=user.id)
            db.add(pending)
        elif pending.status=='rejected':
            raise HTTPException(409,'Pide una invitación al profesorado')
        pending.status='pending'
        db.commit()
        return {'pending':True,'name':room.name}
    admission.code_uses += 1
    return enroll(db, room, user, member)


def enroll(db, room, user, member=None, invitation=None):
    if not member:
        member = ClassMember(class_id=room.id, user_id=user.id, role='student')
        db.add(member)
    member.active = True
    member.role = 'student'
    if invitation is None:
        invitation = db.scalar(select(ClassInvitation).where(
            ClassInvitation.class_id == room.id, ClassInvitation.user_id == user.id,
        ))
    if invitation:
        db.delete(invitation)
    db.flush()
    audit(db, user, 'class_joined', room)
    db.commit()
    return class_summary(db, user, room)


@router.get('/{class_id}')
def get_class(class_id: str, user=Depends(current_user), db=Depends(get_db)):
    return class_summary(db, user, class_by_id(db, user, class_id))


@router.patch('/{class_id}')
def update_class(class_id: str, body: ClassInput, user=Depends(current_user), db=Depends(get_db)):
    begin_class_write(db, user)
    room = class_by_id(db, user, class_id, staff=True, write=True)
    room.name, room.description, room.color = body.name, body.description, body.color
    audit(db, user, 'class_updated', room)
    db.commit()
    return class_summary(db, user, room)


@router.put('/{class_id}/archive')
def archive_class(class_id: str, body: ArchiveInput, user=Depends(current_user), db=Depends(get_db)):
    begin_class_write(db, user)
    room = class_by_id(db, user, class_id, staff=True, write=True, allow_archived=True)
    room.archived = body.archived
    if room.archived:
        room.join_hash = None
        for invitation in db.scalars(select(ClassInvitation).where(ClassInvitation.class_id == room.id)):
            db.delete(invitation)
    audit(db, user, 'class_archived' if room.archived else 'class_reopened', room)
    db.commit()
    return class_summary(db, user, room)


@router.post('/{class_id}/join-code')
def new_code(class_id: str, user=Depends(current_user), db=Depends(get_db)):
    begin_class_write(db, user)
    room = class_by_id(db, user, class_id, staff=True, write=True)
    code = token_urlsafe(18)
    from .education_settings import admission_for, may_invite
    may_invite(db, room, user)
    admission = admission_for(db, room)
    admission.code_uses = 0
    admission.code_expires_at = utcnow()+timedelta(days=7)
    room.join_hash = digest(code)
    audit(db, user, 'class_join_code_rotated', room)
    db.commit()
    return {'join_code': code}


@router.delete('/{class_id}/join-code')
def disable_code(class_id: str, user=Depends(current_user), db=Depends(get_db)):
    begin_class_write(db, user)
    room = class_by_id(db, user, class_id, staff=True, write=True)
    room.join_hash = None
    audit(db, user, 'class_join_code_disabled', room)
    db.commit()
    return {'ok': True}


@router.post('/{class_id}/accept')
def accept_invitation(class_id: str, user=Depends(current_user), db=Depends(get_db)):
    begin_class_write(db, user)
    require_role(user, 'student')
    room = db.scalar(select(LearningClass).where(
        LearningClass.id == class_id, LearningClass.center_id == user.center_id, LearningClass.archived.is_(False),
    ).with_for_update())
    invitation = db.scalar(select(ClassInvitation).where(
        ClassInvitation.class_id == class_id, ClassInvitation.user_id == user.id,
        ClassInvitation.expires_at > utcnow(),
    ))
    if not room or not invitation:
        raise HTTPException(404, 'Invitación no disponible')
    return enroll(db, room, user, member_record(db, room, user.id), invitation)


@router.get('/{class_id}/people')
def people(class_id: str, user=Depends(current_user), db=Depends(get_db)):
    room = class_by_id(db, user, class_id)
    roster = [{'id': member.id, 'name': member.display_name, 'role': member.role} for member in active_members(db, room)
              if user.role != 'student' or member.role == 'teacher' or member.id == user.id]
    teams_query = select(ClassTeam).where(ClassTeam.class_id == room.id).order_by(ClassTeam.name)
    if user.role == 'student':
        teams_query = teams_query.join(ClassTeamMember).where(ClassTeamMember.student_id == user.id)
    teams = []
    active_ids = {item['id'] for item in roster}
    for team in db.scalars(teams_query):
        member_ids = list(db.scalars(select(ClassTeamMember.student_id).where(ClassTeamMember.team_id == team.id)))
        teams.append({**record(team), 'students': [ident for ident in member_ids if ident in active_ids]})
    return {'members': roster, 'teams': teams}


def center_account(db, room, username, role):
    target = db.scalar(select(User).where(User.center_id == room.center_id, User.username == username,
                                         User.active.is_(True), User.role == role))
    if not target:
        raise HTTPException(404, 'Cuenta no disponible para esta clase')
    return target


@router.post('/{class_id}/invitations', status_code=201)
def invite(class_id: str, body: MemberInput, user=Depends(current_user), db=Depends(get_db)):
    begin_class_write(db, user)
    room = class_by_id(db, user, class_id, staff=True, write=True)
    from .education_settings import may_invite
    may_invite(db, room, user)
    target = center_account(db, room, body.username, 'student')
    member = member_record(db, room, target.id)
    if member and member.active and member.role == 'student':
        raise HTTPException(409, 'El alumno ya está inscrito')
    invite = db.scalar(select(ClassInvitation).where(
        ClassInvitation.class_id == room.id, ClassInvitation.user_id == target.id,
    ))
    if not invite:
        invite = ClassInvitation(class_id=room.id, user_id=target.id)
        db.add(invite)
    invite.expires_at = utcnow() + timedelta(days=7)
    notify(db, target.id, 'Invitación a una clase', 'Puedes aceptarla en Clases durante siete días.', 'class')
    audit(db, user, 'class_student_invited', room, {'user_id': target.id})
    db.commit()
    return {'expires_at': invite.expires_at.isoformat()}


@router.post('/{class_id}/teachers', status_code=201)
def add_teacher(class_id: str, body: MemberInput, user=Depends(current_user), db=Depends(get_db)):
    begin_class_write(db, user)
    room = class_by_id(db, user, class_id, staff=True, write=True)
    target = center_account(db, room, body.username, 'teacher')
    member = member_record(db, room, target.id)
    if not member:
        member = ClassMember(class_id=room.id, user_id=target.id, role='teacher')
        db.add(member)
    member.role, member.active = 'teacher', True
    invitation = db.scalar(select(ClassInvitation).where(
        ClassInvitation.class_id == room.id, ClassInvitation.user_id == target.id,
    ))
    if invitation:
        db.delete(invitation)
    audit(db, user, 'class_teacher_added', room, {'user_id': target.id})
    db.commit()
    return {'id': target.id, 'name': target.display_name, 'role': 'teacher'}


@router.delete('/{class_id}/members/{user_id}')
def remove_member(class_id: str, user_id: str, user=Depends(current_user), db=Depends(get_db)):
    begin_class_write(db, user)
    room = class_by_id(db, user, class_id, staff=True, write=True)
    from .education_settings import may_invite
    may_invite(db,room,user)
    member = member_record(db, room, user_id)
    if not member or not member.active:
        raise HTTPException(404, 'Miembro no disponible')
    if member.role == 'teacher' and user.role != 'admin':
        if not any(teacher.id != user_id for teacher in active_members(db, room, 'teacher')):
            raise HTTPException(409, 'Añade otro profesor responsable antes de retirar a este')
    member.active = False
    invite = db.scalar(select(ClassInvitation).where(
        ClassInvitation.class_id == room.id, ClassInvitation.user_id == user_id,
    ))
    if invite:
        db.delete(invite)
    audit(db, user, 'class_member_removed', room, {'user_id': user_id})
    db.commit()
    return {'ok': True}


@router.post('/{class_id}/teams', status_code=201)
def create_team(class_id: str, body: TeamInput, user=Depends(current_user), db=Depends(get_db)):
    begin_class_write(db, user)
    room = class_by_id(db, user, class_id, staff=True, write=True)
    chosen = set(body.students)
    if len(chosen) != len(body.students) or not chosen <= {member.id for member in active_members(db, room, 'student')}:
        raise HTTPException(422, 'Selecciona alumnos distintos de esta clase')
    if db.scalar(select(ClassTeamMember.id).where(
        ClassTeamMember.class_id == room.id, ClassTeamMember.student_id.in_(chosen),
    ).limit(1)):
        raise HTTPException(409, 'Un alumno seleccionado ya pertenece a un equipo')
    team = ClassTeam(class_id=room.id, name=body.name)
    db.add(team)
    db.flush()
    db.add_all(ClassTeamMember(team_id=team.id, class_id=room.id, student_id=ident) for ident in body.students)
    audit(db, user, 'class_team_created', team)
    db.commit()
    return {**record(team), 'students': body.students}


def authors(records, db):
    names = dict(db.execute(select(User.id, User.display_name).where(
        User.id.in_({entry.author_id for entry in records if entry.author_id}),
    )).all())
    return [{**record(entry), 'author_name': names.get(entry.author_id, 'Cuenta eliminada')} for entry in records]


@router.get('/{class_id}/posts')
def list_posts(class_id: str, user=Depends(current_user), db=Depends(get_db)):
    room = class_by_id(db, user, class_id)
    rows = list(db.scalars(select(ClassPost).where(ClassPost.class_id == room.id, ClassPost.hidden.is_(False))
                          .order_by(ClassPost.pinned.desc(), ClassPost.created_at.desc()).limit(100)))
    return authors(rows, db)


@router.post('/{class_id}/posts', status_code=201)
def publish_post(class_id: str, body: PostInput, user=Depends(current_user), db=Depends(get_db)):
    begin_class_write(db, user)
    room = class_by_id(db, user, class_id, staff=True, write=True)
    post = ClassPost(class_id=room.id, author_id=user.id, **body.model_dump())
    db.add(post)
    db.flush()
    audit(db, user, 'class_post_published', post)
    notify_class(db, room, user, 'Aviso nuevo en ' + room.name)
    db.commit()
    return authors([post], db)[0]


def post_for(db, room, post_id):
    post = db.scalar(select(ClassPost).where(
        ClassPost.class_id == room.id, ClassPost.id == post_id, ClassPost.hidden.is_(False),
    ))
    if not post:
        raise HTTPException(404, 'Publicación no disponible')
    return post


@router.put('/{class_id}/posts/{post_id}')
def edit_post(class_id: str, post_id: str, body: PostInput, user=Depends(current_user), db=Depends(get_db)):
    begin_class_write(db, user)
    room = class_by_id(db, user, class_id, staff=True, write=True)
    post = post_for(db, room, post_id)
    post.title, post.content, post.pinned, post.comments_open = body.title, body.content, body.pinned, body.comments_open
    audit(db, user, 'class_post_edited', post)
    db.commit()
    return authors([post], db)[0]


@router.delete('/{class_id}/posts/{post_id}')
def hide_post(class_id: str, post_id: str, user=Depends(current_user), db=Depends(get_db)):
    begin_class_write(db, user)
    room = class_by_id(db, user, class_id, staff=True, write=True)
    post = post_for(db, room, post_id)
    post.hidden = True
    audit(db, user, 'class_post_hidden', post)
    db.commit()
    return {'ok': True}


@router.get('/{class_id}/posts/{post_id}/comments')
def list_comments(class_id: str, post_id: str, user=Depends(current_user), db=Depends(get_db)):
    post = post_for(db, class_by_id(db, user, class_id), post_id)
    rows = list(db.scalars(select(ClassComment).where(ClassComment.post_id == post.id, ClassComment.hidden.is_(False))
                          .order_by(ClassComment.created_at.desc()).limit(200)))
    return authors(rows[::-1], db)


@router.post('/{class_id}/posts/{post_id}/comments', status_code=201)
def add_comment(class_id: str, post_id: str, body: CommentInput, user=Depends(current_user), db=Depends(get_db)):
    begin_class_write(db, user)
    post = post_for(db, class_by_id(db, user, class_id, write=True), post_id)
    if not post.comments_open:
        raise HTTPException(403, 'Esta publicación tiene los comentarios cerrados')
    comment = ClassComment(post_id=post.id, author_id=user.id, content=body.content)
    db.add(comment)
    db.commit()
    return authors([comment], db)[0]


@router.delete('/{class_id}/posts/{post_id}/comments/{comment_id}')
def hide_comment(class_id: str, post_id: str, comment_id: str, user=Depends(current_user), db=Depends(get_db)):
    begin_class_write(db, user)
    post = post_for(db, class_by_id(db, user, class_id, write=True), post_id)
    comment = db.scalar(select(ClassComment).where(
        ClassComment.post_id == post.id, ClassComment.id == comment_id, ClassComment.hidden.is_(False),
    ))
    if not comment or (user.role == 'student' and comment.author_id != user.id):
        raise HTTPException(404, 'Comentario no disponible')
    comment.hidden = True
    audit(db, user, 'class_comment_hidden', comment)
    db.commit()
    return {'ok': True}


@router.get('/{class_id}/topics')
def topics(class_id: str, user=Depends(current_user), db=Depends(get_db)):
    room = class_by_id(db, user, class_id)
    return [record(topic) for topic in db.scalars(select(ClassTopic).where(ClassTopic.class_id == room.id)
                                                 .order_by(ClassTopic.name).limit(200))]


@router.post('/{class_id}/topics', status_code=201)
def create_topic(class_id: str, body: TopicInput, user=Depends(current_user), db=Depends(get_db)):
    begin_class_write(db, user)
    room = class_by_id(db, user, class_id, staff=True, write=True)
    topic = ClassTopic(class_id=room.id, name=body.name)
    db.add(topic)
    db.flush()
    audit(db, user, 'class_topic_added', topic)
    db.commit()
    return record(topic)
