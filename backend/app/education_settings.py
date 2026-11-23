"""Class admissions, teacher-only solutions and reviewable assessment settings."""
from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field, model_validator
from sqlalchemy import func, select

from .auth import current_user, get_db
from .class_models import ClassActivity, ClassInvitation, ClassMember, ClassSubmission, LearningClass
from .class_policy import begin_class_write, class_by_id, visible_classes
from .classes import enroll, member_record
from .classwork import activity_for
from .db import utcnow
from .models import Center, Course, Group, User
from .nebula_models import ClassAdmission, ClassEvaluation, ClassJoinRequest, ClassSolution, GroupTutorship
from .policy import audit, require_role
from .schemas import Input
from .serializers import record

router = APIRouter(tags=['Organización educativa'])


def admission_for(db, room):
    row = db.scalar(select(ClassAdmission).where(ClassAdmission.class_id == room.id))
    if not row:
        row = ClassAdmission(class_id=room.id, teacher_invitations=True, review_codes=False,
                             code_expires_at=utcnow()+timedelta(days=7), code_limit=30, code_uses=0)
        db.add(row)
        db.flush()
    return row


def may_invite(db, room, user):
    if user.role != 'admin' and not admission_for(db, room).teacher_invitations:
        raise HTTPException(403, 'La administración ha cerrado las invitaciones docentes de esta clase')


class AdmissionInput(Input):
    teacher_invitations: bool = True
    review_codes: bool = False
    code_limit: int = Field(default=30, ge=1, le=200)


class DecisionInput(Input):
    approve: bool


@router.get('/classes/{class_id}/admission')
def admission(class_id: str, user=Depends(current_user), db=Depends(get_db)):
    room = class_by_id(db, user, class_id, staff=True)
    result = record(admission_for(db, room))
    db.commit()
    return result


@router.put('/classes/{class_id}/admission')
def save_admission(class_id: str, body: AdmissionInput, user=Depends(current_user), db=Depends(get_db)):
    begin_class_write(db, user)
    require_role(user, 'admin')
    room = class_by_id(db, user, class_id, staff=True, write=True)
    row = admission_for(db, room)
    row.teacher_invitations, row.review_codes, row.code_limit = body.teacher_invitations, body.review_codes, body.code_limit
    audit(db, user, 'class_admission_updated', room)
    db.commit()
    return record(row)


@router.get('/classes/{class_id}/invitations')
def invitations(class_id: str, user=Depends(current_user), db=Depends(get_db)):
    room = class_by_id(db, user, class_id, staff=True)
    return [{**record(invite), 'name':name} for invite,name in db.execute(select(ClassInvitation,User.display_name)
        .join(User,User.id==ClassInvitation.user_id).where(ClassInvitation.class_id==room.id))]


@router.delete('/classes/{class_id}/invitations/{invitation_id}')
def revoke_invitation(class_id: str, invitation_id: str, user=Depends(current_user), db=Depends(get_db)):
    begin_class_write(db, user)
    room = class_by_id(db, user, class_id, staff=True, write=True)
    may_invite(db, room, user)
    row = db.scalar(select(ClassInvitation).where(ClassInvitation.class_id==room.id, ClassInvitation.id==invitation_id))
    if not row:
        raise HTTPException(404,'Invitación no disponible')
    db.delete(row)
    audit(db,user,'class_invitation_revoked',room)
    db.commit()
    return {'ok':True}


@router.get('/classes/{class_id}/requests')
def requests(class_id: str, user=Depends(current_user), db=Depends(get_db)):
    room = class_by_id(db,user,class_id,staff=True)
    return [{**record(row),'name':name} for row,name in db.execute(select(ClassJoinRequest,User.display_name)
        .join(User,User.id==ClassJoinRequest.user_id).where(ClassJoinRequest.class_id==room.id,
                                                       ClassJoinRequest.status=='pending'))]


@router.post('/classes/{class_id}/requests/{request_id}')
def decide(class_id: str, request_id: str, body: DecisionInput, user=Depends(current_user), db=Depends(get_db)):
    begin_class_write(db,user)
    room=class_by_id(db,user,class_id,staff=True,write=True)
    may_invite(db,room,user)
    row=db.scalar(select(ClassJoinRequest).where(ClassJoinRequest.class_id==room.id,ClassJoinRequest.id==request_id,
                                               ClassJoinRequest.status=='pending'))
    target=db.get(User,row.user_id) if row else None
    if not target or not target.active or target.role!='student' or target.center_id!=room.center_id:
        raise HTTPException(404,'Solicitud no disponible')
    row.status='approved' if body.approve else 'rejected'
    audit(db,user,'class_join_request_decided',row)
    if body.approve:
        admission=admission_for(db,room)
        if admission.code_uses>=admission.code_limit:
            raise HTTPException(409,'El código ha agotado sus inscripciones')
        admission.code_uses+=1
        return enroll(db,room,target,member_record(db,room,target.id))
    db.commit()
    return {'ok':True}


class WeightsInput(Input):
    weights: dict[str, Annotated[int,Field(ge=0,le=100)]]

    @model_validator(mode='after')
    def valid_weights(self):
        if set(self.weights) != {'activities','exams','projects','participation'} or sum(self.weights.values()) != 100:
            raise ValueError('Reparte 100 puntos entre actividades, exámenes, proyectos y participación')
        return self


@router.get('/classes/{class_id}/evaluation')
def evaluation(class_id: str, user=Depends(current_user), db=Depends(get_db)):
    room=class_by_id(db,user,class_id)
    row=db.scalar(select(ClassEvaluation).where(ClassEvaluation.class_id==room.id))
    return {'weights':row.weights if row else {}, 'source':'Configuración de la clase', 'simulation':True}


@router.put('/classes/{class_id}/evaluation')
def update_evaluation(class_id: str, body: WeightsInput, user=Depends(current_user), db=Depends(get_db)):
    begin_class_write(db,user)
    room=class_by_id(db,user,class_id,staff=True,write=True)
    row=db.scalar(select(ClassEvaluation).where(ClassEvaluation.class_id==room.id))
    if not row:
        row=ClassEvaluation(class_id=room.id)
        db.add(row)
    row.weights=body.weights
    audit(db,user,'class_evaluation_settings_updated',room)
    db.commit()
    return {'weights':row.weights,'simulation':True}


class SolutionInput(Input):
    content: str = Field(min_length=1,max_length=6000)


@router.get('/classes/{class_id}/activities/{activity_id}/solution')
def solution(class_id: str, activity_id: str, user=Depends(current_user), db=Depends(get_db)):
    room=class_by_id(db,user,class_id,staff=True)
    activity_for(db,user,room,activity_id)
    row=db.scalar(select(ClassSolution).where(ClassSolution.activity_id==activity_id))
    return {'content':row.content if row else ''}


@router.put('/classes/{class_id}/activities/{activity_id}/solution')
def update_solution(class_id: str, activity_id: str, body: SolutionInput, user=Depends(current_user), db=Depends(get_db)):
    begin_class_write(db,user)
    room=class_by_id(db,user,class_id,staff=True,write=True)
    activity_for(db,user,room,activity_id)
    row=db.scalar(select(ClassSolution).where(ClassSolution.activity_id==activity_id))
    if not row:
        row=ClassSolution(activity_id=activity_id)
        db.add(row)
    row.content=body.content
    audit(db,user,'class_solution_updated',room)
    db.commit()
    return {'content':row.content}


def education_overview(db,user):
    rooms=select(LearningClass.id).where(LearningClass.id.in_(visible_classes(user)))
    pending=db.scalar(select(func.count()).select_from(ClassSubmission).join(ClassActivity).where(
        ClassActivity.class_id.in_(rooms),ClassSubmission.status=='submitted')) if user.role!='student' else None
    result={'classes':db.scalar(select(func.count()).select_from(LearningClass).where(LearningClass.id.in_(rooms))),
            'pending_reviews':pending}
    if user.role=='admin':
        from .models import CalendarEvent,Teaching
        result['upcoming_evaluations']=[record(event) for event in db.scalars(select(CalendarEvent).where(
            CalendarEvent.center_id==user.center_id,CalendarEvent.kind=='evaluation',CalendarEvent.starts_at>utcnow())
            .order_by(CalendarEvent.starts_at).limit(10))]
        result['evaluation_groups']=[group.name for group in db.scalars(select(Group).where(Group.center_id==user.center_id).order_by(Group.name))]
        result['teaching']=[{'group':g.name,'teacher':u.display_name,'subject_id':t.subject_id}
            for t,g,u in db.execute(select(Teaching,Group,User).join(Group,Teaching.group_id==Group.id)
                .join(User,Teaching.teacher_id==User.id).where(Group.center_id==user.center_id).limit(150))]
    return result


@router.get('/education/overview')
def overview(user=Depends(current_user),db=Depends(get_db)):
    return education_overview(db,user)


@router.get('/education/organization')
def organization(user=Depends(current_user),db=Depends(get_db)):
    center=db.get(Center,user.center_id)
    allowed=select(LearningClass.group_id).where(LearningClass.id.in_(visible_classes(user)))
    tutors=[{'group':group.name,'teacher':person.display_name,'office_hour':row.office_hour}
        for row,group,person in db.execute(select(GroupTutorship,Group,User).join(Group,Group.id==GroupTutorship.group_id)
            .join(User,User.id==GroupTutorship.teacher_id).where(Group.center_id==user.center_id,
                Group.id.in_(allowed)))]
    org=center.settings.get('organization',{})
    if user.role=='admin':
        ids={org.get(key) for key in ('direction','studies','secretary')}
        persons={p.id:p.display_name for p in db.scalars(select(User).where(User.center_id==user.center_id))}
        org={**{key:persons.get(org.get(key),'Sin asignar') for key in ('direction','studies','secretary')},
             'departments':[{**item,'coordinator':persons.get(item['coordinator_id'],'Sin asignar')}
                            for item in org.get('departments',[])]}
    else:
        org={}
    return {'center':center.name,'fictional':bool(center.settings.get('fictional')),
            'organization':org,'tutors':tutors,'break':center.settings.get('break')}
