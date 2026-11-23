import re
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, text, or_,update,func
from .auth import current_user, get_db
from .models import Memory, Message, Conversation, MemorySummary
from .schemas import MemoryInput
from .learning_schemas import MemoryUpdate
from .serializers import record

router = APIRouter(prefix='/memory', tags=['Memoria privada'])
MADRID = ZoneInfo('Europe/Madrid')


def day_bounds(day):
    try:
        d = date.fromisoformat(day)
    except ValueError:
        raise HTTPException(422, 'Fecha inválida; usa AAAA-MM-DD')
    return datetime.combine(d, time.min, MADRID).astimezone(timezone.utc), datetime.combine(d + timedelta(days=1), time.min, MADRID).astimezone(timezone.utc)


def search_ids(db, entity, query, limit=500):
    tokens = re.findall(r'[^\W_]+', query, flags=re.UNICODE)[:12]
    if not tokens or db.bind.dialect.name != 'sqlite':
        return None
    expression = ' OR '.join('"' + token.replace('"', '') + '"' for token in tokens)
    return list(db.scalars(text('SELECT record_id FROM search_index WHERE search_index MATCH :q AND entity=:e ORDER BY bm25(search_index) LIMIT :n'), {'q':expression, 'e':entity, 'n':limit}))


def searched(stmt, db, model, query):
    if query:
        # ACLs remain on the outer SQL query. Do not cap candidates before ACL filtering.
        if db.bind.dialect.name == 'sqlite':
            tokens = re.findall(r'[^\W_]+', query, flags=re.UNICODE)[:12]
            if tokens:
                expression = ' OR '.join('"' + x + '"' for x in tokens)
                sub = text('SELECT record_id FROM search_index WHERE search_index MATCH :fts AND entity=:entity').bindparams(fts=expression, entity=model.__tablename__)
                stmt = stmt.where(model.id.in_(sub))
            else:
                stmt = stmt.where(model.content.ilike('%' + query.replace('%', '\\%').replace('_', '\\_') + '%', escape='\\'))
        else:
            tokens = re.findall(r'[^\W_]+', query, flags=re.UNICODE)[:12]
            stmt = stmt.where(or_(*(model.content.ilike('%' + x + '%') for x in tokens))) if tokens else stmt.where(model.content == query)
    return stmt


def retrieve_memory(db, user, query='', day=None, limit=30):
    mstmt = searched(select(Memory).where(Memory.user_id == user.id), db, Memory, query)
    tstmt = searched(select(Message).join(Conversation).where(Conversation.user_id == user.id), db, Message, query)
    if day:
        start, end = day_bounds(day)
        mstmt = mstmt.where(or_((Memory.event_at >= start) & (Memory.event_at < end), (Memory.event_at.is_(None)) & (Memory.created_at >= start) & (Memory.created_at < end)))
        tstmt = tstmt.where(Message.created_at >= start, Message.created_at < end)
    memories = [dict(record(m), entity='memory') for m in db.scalars(mstmt.order_by(Memory.created_at.desc()).limit(limit))]
    messages = [dict(record(m), entity='message') for m in db.scalars(tstmt.order_by(Message.created_at.desc()).limit(limit))]
    if query:
        terms = re.findall(r'[^\W_]+', query.casefold())
        def score(r):
            return sum(r['content'].casefold().count(t) for t in terms)
        memories.sort(key=score, reverse=True)
        messages.sort(key=score, reverse=True)
    return {'memories': memories, 'messages': messages}


@router.get('')
def search(q: str = Query(default='', max_length=300), day: str | None = None, user=Depends(current_user), db=Depends(get_db)):
    return retrieve_memory(db, user, q, day)


@router.post('', status_code=201)
def create(body: MemoryInput, user=Depends(current_user), db=Depends(get_db)):
    mem = Memory(user_id=user.id, **body.model_dump())
    db.add(mem)
    db.commit()
    return record(mem)


@router.delete('/{memory_id}')
def remove(memory_id: str, user=Depends(current_user), db=Depends(get_db)):
    obj = db.scalar(select(Memory).where(Memory.id == memory_id, Memory.user_id == user.id))
    if not obj:
        raise HTTPException(404, 'Recuerdo no disponible')
    from .semantic import invalidate
    invalidate(db,user,obj.id)
    db.delete(obj)
    db.commit()
    return {'ok': True}


def summarize_conversation(db, convo):
    count=db.scalar(select(func.count()).select_from(Message).where(Message.conversation_id==convo.id))
    if count < 12:
        return
    rows=list(db.scalars(select(Message).where(Message.conversation_id==convo.id).order_by(Message.created_at.desc(),Message.id.desc()).limit(16)))[::-1]
    summary = db.scalar(select(MemorySummary).where(MemorySummary.conversation_id == convo.id))
    content = 'Resumen extractivo; conserva los mensajes originales.\n' + '\n'.join(f'{r.role}: {r.content[:180]}' for r in rows[-16:])
    if summary:
        summary.content, summary.message_count = content, count
    else:
        db.add(MemorySummary(conversation_id=convo.id, content=content, message_count=count))


@router.patch('/{memory_id}')
def correct_memory(memory_id:str,body:MemoryUpdate,user=Depends(current_user),db=Depends(get_db)):
    obj=db.scalar(select(Memory).where(Memory.id==memory_id,Memory.user_id==user.id))
    if not obj:raise HTTPException(404,'Recuerdo no disponible')
    if obj.updated_at!=body.expected_updated_at:raise HTTPException(409,'El recuerdo ha cambiado; actualiza antes de corregirlo')
    changed=db.execute(update(Memory).where(Memory.id==memory_id,Memory.user_id==user.id,Memory.updated_at==body.expected_updated_at).values(content=body.content,category=body.category,event_at=body.event_at)).rowcount
    if not changed:raise HTTPException(409,'El recuerdo ha cambiado; actualiza antes de corregirlo')
    from .semantic import invalidate
    from .models import MemoryAnnotation
    invalidate(db,user,obj.id)
    annotation=db.scalar(select(MemoryAnnotation).where(MemoryAnnotation.memory_id==obj.id,MemoryAnnotation.user_id==user.id))
    if annotation:annotation.state='provisional';annotation.provenance='Corregido por su titular; pendiente de comprobar'
    db.commit();db.refresh(obj);return record(obj)


def retrieve_summaries(db,user,query,limit=2):
    tokens=[t for t in re.findall(r'[^\W_]+',query) if len(t)>3][:6]
    if not tokens:return []
    stmt=select(MemorySummary).join(Conversation).where(Conversation.user_id==user.id,or_(*(MemorySummary.content.ilike('%'+t+'%') for t in tokens)))
    return [record(s) for s in db.scalars(stmt.order_by(MemorySummary.updated_at.desc()).limit(limit))]
