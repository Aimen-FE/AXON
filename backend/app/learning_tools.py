from datetime import datetime
from sqlalchemy import select,or_
from fastapi import HTTPException
from .models import (Subject,LearnerSubject,LearnerProfile,AcademicTeacher,User,Teaching,
    AssessmentPolicy,KnowledgeSource,CourseUnit,Notification,PersonalTask,Memory)
from .serializers import record
from .knowledge import profile_for,personal_schedule,knowledge_data,subject_for
from .study import prepare_plan
from .grades import calculate
from .education import events_for,assignments_for
from .memory import retrieve_memory,day_bounds

NAMES={'get_my_schedule','get_subjects','get_teachers','query_knowledge','calculate_grade',
       'create_study_plan','get_study_context','get_school_information','get_notifications','create_personal_task','get_pending'}


def subjects_for(db,user):
    stmt=select(Subject).where(Subject.center_id==user.center_id)
    if profile_for(db,user):stmt=stmt.where(Subject.id.in_(select(LearnerSubject.subject_id).where(LearnerSubject.user_id==user.id,LearnerSubject.active.is_(True))))
    else:
        from .policy import group_ids
        stmt=stmt.where(Subject.id.in_(select(Teaching.subject_id).where(Teaching.group_id.in_(group_ids(db,user))))) if user.role!='admin' else stmt
    return [record(s) for s in db.scalars(stmt.order_by(Subject.name))]


def run_learning_tool(db,user,name,args,settings):
    if name=='get_study_context':
        from datetime import timedelta
        from .db import utcnow
        from .models import LearningProgress
        start,end=day_bounds(args.day) if args.day else (utcnow(),utcnow()+timedelta(days=21))
        exams=[e for e in events_for(db,user,kind='exam',start=start,end=end) if e['status']=='published' and (not args.subject_id or e['subject_id']==args.subject_id)]
        subject_ids={e['subject_id'] for e in exams}
        result={'exams':exams,'units':[record(u) for u in db.scalars(select(CourseUnit).where(CourseUnit.owner_id==user.id,CourseUnit.subject_id.in_(subject_ids)))],'progress':[record(p) for p in db.scalars(select(LearningProgress).where(LearningProgress.user_id==user.id))]}
    elif name=='get_school_information':
        from .models import Center
        center=db.get(Center,user.center_id);profile=profile_for(db,user)
        from .atlas import context as core_context
        from .documents import retrieve_documents
        result={'identity':core_context(db,user),'institutional_fragments':retrieve_documents(db,user,args.query,limit=4,institutional=True),'name':center.name,'public_info':center.settings.get('public_info',{}),'calendar':profile.preferences.get('school_calendar',{}) if profile else {},'question':args.query,'sources':[record(s) for s in db.scalars(select(KnowledgeSource).where(KnowledgeSource.owner_id==user.id,KnowledgeSource.kind.in_(['school_directory','school_calendar'])))]}
    elif name=='get_my_schedule':
        if profile_for(db,user):result=personal_schedule(db,user,args.day,args.subject_id)
        else:
            from .tools import run_tool
            result={'lessons':run_tool(db,user,'query_schedule',{'day':args.day,'query':args.query},settings)['result'],'pending_blocks':[]}
    elif name=='get_subjects':result=subjects_for(db,user)
    elif name=='get_teachers':
        result=[record(t) for t in db.scalars(select(AcademicTeacher).where(AcademicTeacher.owner_id==user.id))]
        if args.subject_id:result=[t for t in result if t['subject_id']==args.subject_id]
        elif profile_for(db,user):
            selected={s['id'] for s in subjects_for(db,user)};result=[t for t in result if t['subject_id'] in selected]
        if not result:
            from .policy import group_ids
            result=[{'display_name':u.display_name,'subject_id':t.subject_id,'group_id':t.group_id,'source':'Asignación académica del sistema'} for t,u in db.execute(select(Teaching,User).join(User,User.id==Teaching.teacher_id).where(Teaching.group_id.in_(group_ids(db,user)),User.center_id==user.center_id)) if not args.subject_id or t.subject_id==args.subject_id]
    elif name=='query_knowledge':
        result=knowledge_data(db,user,args.subject_id)
        # Do not return full documents through the context interface.
        result['policies']=[{k:v for k,v in p.items() if k!='rules_text'} for p in result['policies']]
        result['units']=[dict(u,content=u['content'][:900]) for u in result['units']]
        result['question']=args.query
        if not result['policies'] and not result['units']:
            from .documents import retrieve_documents
            result['fragments']=retrieve_documents(db,user,args.query,limit=3)
    elif name=='calculate_grade':result=calculate(db,user,args)
    elif name=='create_study_plan':return prepare_plan(db,user,args)
    elif name=='get_notifications':result=[record(n) for n in db.scalars(select(Notification).where(Notification.user_id==user.id).order_by(Notification.created_at.desc()).limit(15))]
    elif name=='create_personal_task':
        if args.subject_id:subject_for(db,user,args.subject_id)
        task=PersonalTask(user_id=user.id,**args.model_dump());db.add(task);db.flush();result=record(task)
    elif name=='get_pending':
        personal=[record(t) for t in db.scalars(select(PersonalTask).where(PersonalTask.user_id==user.id,PersonalTask.completed.is_(False)).order_by(PersonalTask.due_at))]
        reminders=[dict(record(m),entity='memory') for m in db.scalars(select(Memory).where(Memory.user_id==user.id,or_(Memory.category=='reminder',*(Memory.content.ilike('%'+word+'%') for word in ('debo','repasar','pendiente','tengo')))).order_by(Memory.updated_at.desc()).limit(30))]
        result={'tasks':assignments_for(db,user),'personal_tasks':personal,'memory':{'memories':reminders,'messages':[]}}
    else:raise HTTPException(404,'Herramienta académica no disponible')
    return {'status':'completed','tool':name,'result':result}
