"""One search surface, independent SQL ACLs for every result family."""
from fastapi import APIRouter,Depends,Query
from sqlalchemy import select,or_
from .auth import current_user,get_db
from .models import Subject,Document,CourseUnit,Memory,Conversation,Message,CalendarEvent,PersonalTask,Assignment,Teaching
from .policy import document_filter,event_filter,group_ids
from .learning_tools import subjects_for

router=APIRouter(prefix='/search',tags=['Búsqueda universal autorizada'])

@router.get('')
def search(q:str=Query(min_length=2,max_length=200),user=Depends(current_user),db=Depends(get_db)):
    escaped='%'+q.replace('\\','\\\\').replace('%','\\%').replace('_','\\_')+'%'
    like=lambda col:col.ilike(escaped,escape='\\')
    results=[]
    def add(kind,obj,title,snippet,page,**extra):results.append({'kind':kind,'id':obj.id,'title':title[:180],'snippet':snippet[:400],'page':page,**extra})
    selected={s['id'] for s in subjects_for(db,user)}
    for obj in db.scalars(select(Subject).where(Subject.center_id==user.center_id,Subject.id.in_(selected),like(Subject.name)).limit(10)):add('subject',obj,obj.name,'Asignatura autorizada','subjects')
    for obj in db.scalars(select(Document).where(document_filter(db,user),or_(like(Document.title),like(Document.source))).limit(15)):add('document',obj,obj.title,obj.source,'documents',document_id=obj.id)
    # Content matches use the existing chunk search, which keeps the outer document ACL.
    from .documents import retrieve_documents
    seen={r['id'] for r in results if r['kind']=='document'}
    for frag in retrieve_documents(db,user,q,limit=10):
        if frag['document_id'] not in seen:
            results.append({'kind':'document','id':frag['document_id'],'title':frag['title'],'snippet':frag['content'][:400],'page':'documents','document_id':frag['document_id'],'location':frag['location']});seen.add(frag['document_id'])
    for obj in db.scalars(select(CourseUnit).where(CourseUnit.owner_id==user.id,or_(like(CourseUnit.title),like(CourseUnit.content))).limit(10)):add('unit',obj,obj.title,obj.content,'knowledge')
    for obj in db.scalars(select(CalendarEvent).where(event_filter(db,user),or_(like(CalendarEvent.title),like(CalendarEvent.description))).limit(15)):add('exam' if obj.kind=='exam' else 'event',obj,obj.title,obj.description,'calendar',event_id=obj.id)
    for obj in db.scalars(select(Assignment).where(Assignment.center_id==user.center_id,Assignment.group_id.in_(group_ids(db,user)),or_(like(Assignment.title),like(Assignment.description))).limit(10)):add('assignment',obj,obj.title,obj.description,'tasks')
    for obj in db.scalars(select(PersonalTask).where(PersonalTask.user_id==user.id,or_(like(PersonalTask.title),like(PersonalTask.description))).limit(10)):add('personal_task',obj,obj.title,obj.description,'tasks')
    for obj in db.scalars(select(Memory).where(Memory.user_id==user.id,like(Memory.content)).limit(15)):add('memory',obj,'Recuerdo privado',obj.content,'memory')
    convos=list(db.scalars(select(Conversation).where(Conversation.user_id==user.id,or_(like(Conversation.title),Conversation.id.in_(select(Message.conversation_id).where(like(Message.content))))).order_by(Conversation.updated_at.desc()).limit(15)))
    for obj in convos:
        message=db.scalar(select(Message).where(Message.conversation_id==obj.id,like(Message.content)).order_by(Message.created_at.desc()).limit(1))
        add('conversation',obj,obj.title,message.content if message else 'Conversación propia','chat',conversation_id=obj.id)
    return {'query':q,'results':results[:100],'scope':'Permisos comprobados por familia de datos; conversaciones y recuerdos solo propios'}
