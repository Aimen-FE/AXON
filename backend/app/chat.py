import asyncio
import logging
import re
from fastapi import APIRouter,Depends,HTTPException,Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from .auth import current_user,get_db
from .db import utcnow
from .models import Conversation,Message,Group,Subject,Teaching
from .schemas import ConversationCreate,ChatInput
from .serializers import record
from .memory import retrieve_memory,summarize_conversation,MADRID
from .documents import retrieve_documents
from .tools import run_tool,CATALOG,parse_tool
from .agent import plan,format_results,norm,parse_day
from .policy import group_ids

router=APIRouter(prefix='/conversations',tags=['Conversaciones privadas'])
logger=logging.getLogger('axon.chat')


def own_conversation(db,user,ident):
    obj=db.scalar(select(Conversation).where(Conversation.id==ident,Conversation.user_id==user.id))
    if not obj:raise HTTPException(404,'Conversación no disponible')
    return obj


@router.get('')
def conversations(q:str='',user=Depends(current_user),db=Depends(get_db)):
    if len(q)>200:raise HTTPException(422,'Búsqueda demasiado larga')
    stmt=select(Conversation).where(Conversation.user_id==user.id)
    if q:stmt=stmt.where(Conversation.title.ilike('%'+q.replace('%','\\%').replace('_','\\_')+'%',escape='\\'))
    return [record(x) for x in db.scalars(stmt.order_by(Conversation.updated_at.desc()).limit(150))]


@router.post('',status_code=201)
def create(body:ConversationCreate,user=Depends(current_user),db=Depends(get_db)):
    if user.preferences.get('public_guest'):
        from sqlalchemy import func
        if db.scalar(select(func.count()).select_from(Conversation).where(Conversation.user_id==user.id))>=10:raise HTTPException(429,'Puedes abrir hasta diez conversaciones en esta sesión temporal')
    obj=Conversation(user_id=user.id,title=body.title)
    db.add(obj)
    db.commit()
    return record(obj)


@router.get('/{conversation_id}')
def history(conversation_id:str,user=Depends(current_user),db=Depends(get_db)):
    obj=own_conversation(db,user,conversation_id)
    return {'conversation':record(obj),'messages':[record(x) for x in db.scalars(select(Message).where(Message.conversation_id==obj.id).order_by(Message.created_at,Message.id))]}


@router.post('/{conversation_id}/messages')
async def send(conversation_id:str,body:ChatInput,request:Request,user=Depends(current_user),db=Depends(get_db)):
    convo=own_conversation(db,user,conversation_id)
    previous=db.scalar(select(Message).where(Message.conversation_id==convo.id,Message.client_id==body.client_id))
    if previous:
        answer=db.scalar(select(Message).where(Message.in_reply_to==previous.id))
        if answer:return {'user_message':record(previous),'assistant_message':record(answer)}
        raise HTTPException(409,'El mensaje ya está registrado. Actualiza el historial; puedes enviar otro mensaje si la respuesta se interrumpió')
    # Bound simultaneous inference requests; never discard an accepted user message.
    if request.app.state.chat_inflight>=4:raise HTTPException(429,'AXON está atendiendo otras peticiones. Inténtalo en unos instantes')
    from .guest import consume_query
    consume_query(db,user,request)
    request.app.state.chat_inflight+=1
    msg=Message(conversation_id=convo.id,role='user',content=body.content,client_id=body.client_id)
    db.add(msg)
    convo.updated_at=utcnow()
    if convo.title=='Nueva conversación':convo.title=body.content[:100]
    try:
        db.commit()
    except IntegrityError:
        request.app.state.chat_inflight-=1
        db.rollback()
        raise HTTPException(409,'Este mensaje ya se ha enviado')
    details={'engine':'structured','tools':[],'citations':[],'actions':[],'event_ids':[]}
    try:
        rows=list(db.scalars(select(Message).where(Message.conversation_id==convo.id).order_by(Message.created_at.desc()).limit(12)))[::-1]
        previous_user=next((m.content for m in reversed(rows[:-1]) if m.role=='user'),None)
        from .providers import local_policy
        runtime_policy=local_policy(db,user,request.app.state.settings)
        if request.app.state.settings.full_demo:runtime_policy.update(output_tokens=350,timeout_seconds=60,queue_seconds=10)
        elif request.app.state.settings.public_demo:runtime_policy.update(output_tokens=220,timeout_seconds=45,queue_seconds=10)
        from .orchestrator import advanced_plan,execute
        from .atlas import identity_intent,identity_answer,context as core_context,available_functions
        previous_answer=next((m for m in reversed(rows[:-1]) if m.role=='assistant'),None)
        intent=identity_intent(body.content,previous_answer.details.get('identity_intent') if previous_answer else None)
        proposed={} if intent else advanced_plan(db,user,body.content) or plan(db,user,body.content,previous_user)
        # Optional model planning for explicit academic requests outside deterministic intents.
        if not intent and not proposed and any(word in norm(body.content) for word in ('fija ', 'prueba ', 'evaluacion', 'necesito publicar', 'quisiera programar')):
            allowed_names = {'query_exams','query_calendar','query_schedule','query_assignments','query_subjects','search_documents','search_memory','publish_exam','create_assignment','create_event'}
            if any(w in norm(body.content) for w in ('prueba ', 'evaluacion')):
                allowed_names = {'publish_exam','query_exams'}
            specs = [{'type':'function','function':{'name':name,'description':spec.description,'parameters':spec.schema.model_json_schema()}} for name,spec in CATALOG.items() if name in allowed_names and user.role in spec.roles]
            allowed_groups = group_ids(db,user)
            metadata = {'runtime_policy':runtime_policy,'today':utcnow().isoformat(),'timezone':'Europe/Madrid',
                        'groups':[{'id':g.id,'name':g.name} for g in db.scalars(select(Group).where(Group.id.in_(allowed_groups)))],
                        'subjects':[{'id':s.id,'name':s.name} for s in db.scalars(select(Subject).where(Subject.center_id==user.center_id,Subject.id.in_(select(Teaching.subject_id).where(Teaching.group_id.in_(allowed_groups)))))]}
            model_calls = await request.app.state.ai.propose(body.content,specs,metadata)
            if model_calls:
                for name,args in model_calls:
                    if name not in allowed_names:
                        raise HTTPException(403,'La propuesta incluye una herramienta no autorizada para el planificador')
                    if CATALOG[name].level == 3:
                        if name == 'create_event' and args.get('visibility','group') == 'personal':
                            raise HTTPException(422,'Los recordatorios privados se preparan con una petición explícita al catálogo personal')
                        if not parse_day(body.content) or not re.search(r'\b\d{1,2}:\d{2}\b',body.content):
                            raise HTTPException(422,'Indica fecha y hora antes de preparar una propuesta académica')
                        parsed = parse_tool(user,name,args)
                        instant = getattr(parsed,'starts_at',None) or getattr(parsed,'due_at',None)
                        if instant:
                            requested = re.search(r'\b(\d{1,2}):(\d{2})\b',body.content)
                            local = instant.astimezone(MADRID)
                            if local.date()!=parse_day(body.content) or (local.hour,local.minute)!=(int(requested.group(1)),int(requested.group(2))):
                                raise HTTPException(422,'La fecha u hora propuesta por el modelo no coincide con tu petición. Usa el formulario o la expresión «programa un examen».')
                proposed = {'calls':model_calls}
                details['planner'] = 'ollama'
        if intent:
            content,details=identity_answer(db,user,intent)
        elif proposed.get('clarification'):
            content=proposed['clarification']
        elif proposed.get('calls'):
            from .extensions import require_module
            require_module(db,user,'agent')
            db.commit()
            results,run,failures=await execute(request.app,user,convo.id,msg.id,proposed)
            details['run_id']=run['id']
            details['run_status']=run['status']
            for result in results:
                name=result['tool']
                details['tools'].append({'name':name,'status':result['status']})
                if result.get('action'):details['actions'].append(result['action'])
                if name in ('create_event','publish_exam') and result['status']=='completed' and result.get('result',{}).get('id'):details['event_ids'].append(result['result']['id'])
            content,details['citations']=format_results(db,user,results,proposed.get('study',False))
            if failures:content+='\n\nPasos sin completar:\n'+'\n'.join('• '+failure for failure in failures)
            if run['status'] in ('partial','cancelled'):content+='\n\nEl plan ha quedado '+('cancelado' if run['status']=='cancelled' else 'parcialmente completado')+'. Consulta el detalle de pasos; los resultados terminados se han conservado.'
            if not content.strip():content='No se ha completado ningún paso. Consulta el plan para revisar el motivo.'
            if proposed.get('assumption'):content=proposed['assumption']+'\n\n'+content
        else:
            from .semantic import search_semantic,semantic_status
            from .advanced_schemas import SemanticQuery
            from .extensions import enabled
            recall=search_semantic(db,user,SemanticQuery(query=body.content[:300],limit=4),request.app.state.settings) if (not request.app.state.settings.public_demo or request.app.state.settings.full_demo) and len(body.content.strip())>=2 and enabled(db,user,'semantic') and semantic_status(request.app.state.settings)['available'] else retrieve_memory(db,user,body.content[:300],limit=4)
            context={'runtime_policy':runtime_policy,'base100':core_context(db,user),'memories':recall['memories'],
                     'documents':retrieve_documents(db,user,body.content[:300],limit=3),
                     'capabilities':list(available_functions(db,user)),
                     'timezone':'Europe/Madrid','today':utcnow().astimezone(MADRID).date().isoformat()}
            from .knowledge import profile_for
            profile=profile_for(db,user)
            if profile:context['learning_preferences']={k:v for k,v in profile.preferences.items() if isinstance(v,(str,bool,int))}
            from .memory import retrieve_summaries
            context['conversation_summaries']=retrieve_summaries(db,user,body.content[:200])
            generation=asyncio.create_task(request.app.state.ai.generate([record(m) for m in rows],context))
            request.app.state.active_generations[msg.id]=(user.id,convo.id,body.client_id,generation)
            try:content,engine=await generation
            except asyncio.CancelledError:
                if asyncio.current_task().cancelling() or not generation.cancelled():raise
                content,engine='Respuesta detenida. Tu mensaje se ha conservado.','cancelled'
            finally:request.app.state.active_generations.pop(msg.id,None)
            details['engine']=engine
            from .relevance import attributed_citations
            content,details['citations']=attributed_citations(content,context['documents']) if content and engine=='ollama' else (content,[])
            if not content:
                content=(('Modo de demostración: ' if engine=='simulated' else '')+('La IA local está ocupada; prueba en unos instantes. ' if engine=='local_busy' else 'El modelo local no está disponible. ')+'Puedo consultar tus exámenes, tareas y horarios; guardar y buscar recuerdos privados; y preparar propuestas autorizadas. Prueba «¿Qué exámenes tengo?» o «Recuerda que prefiero estudiar por la tarde».')
        if public_session_ended(db,user,request):return ended_response()
        answer=Message(conversation_id=convo.id,role='assistant',content=content,in_reply_to=msg.id,details=details)
        db.add(answer)
        db.flush()
        summarize_conversation(db,convo)
        db.commit()
    except HTTPException as exc:
        db.rollback()
        if public_session_ended(db,user,request):return ended_response()
        detail=exc.detail if isinstance(exc.detail,str) else exc.detail.get('message','Revisa los datos')
        answer=Message(conversation_id=convo.id,role='assistant',content='No he completado la operación. '+detail,in_reply_to=msg.id,
                       details={'engine':'structured','error':True,'tools':[],'actions':[],'citations':[]})
        db.add(answer)
        db.commit()
    except asyncio.CancelledError:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        if public_session_ended(db,user,request):return ended_response()
        logger.error('No se pudo completar una respuesta de AXON (%s)',type(exc).__name__)
        answer=Message(conversation_id=convo.id,role='assistant',content='El mensaje se ha conservado, pero no he podido completar la operación. No se ha confirmado ningún cambio académico.',in_reply_to=msg.id,details={'engine':'error','error':True})
        db.add(answer)
        db.commit()
    finally:
        request.app.state.chat_inflight-=1
    return {'user_message':record(msg),'assistant_message':record(answer)}

@router.post('/{conversation_id}/cancel/{client_id}')
async def cancel_response(conversation_id:str,client_id:str,request:Request,user=Depends(current_user),db=Depends(get_db)):
    own_conversation(db,user,conversation_id)
    cancelled=False
    for owner,convo,ident,task in list(request.app.state.active_generations.values()):
        if owner==user.id and convo==conversation_id and ident==client_id:task.cancel();cancelled=True
    return {'cancelled':cancelled,'message':'Se ha solicitado detener la respuesta' if cancelled else 'La respuesta ha terminado o el plan se puede detener desde sus pasos'}


def public_session_ended(db,user,request):
    if not request.app.state.settings.public_demo:return False
    if request.app.state.settings.full_demo:
        from .models import TeacherDemoSession
        return not db.scalar(select(TeacherDemoSession.id).where(TeacherDemoSession.user_id==user.id,TeacherDemoSession.revoked.is_(False),TeacherDemoSession.expires_at>utcnow()))
    from .models import GuestSession
    return not db.scalar(select(GuestSession.id).where(GuestSession.user_id==user.id,GuestSession.revoked.is_(False),GuestSession.expires_at>utcnow()))

def ended_response():
    from fastapi.responses import JSONResponse
    return JSONResponse({'detail':'La sesión temporal ha terminado'},401)
