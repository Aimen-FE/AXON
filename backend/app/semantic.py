"""Owner-scoped hybrid memory search. Local model files are provisioned explicitly."""
import hashlib
import json
import threading
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select, delete, or_
from .auth import current_user, get_db
from .models import Memory, Message, Conversation, MemoryAnnotation, MemoryRelation, SemanticVector
from .advanced_schemas import SemanticQuery, AnnotationInput
from .serializers import record
from .memory import day_bounds, retrieve_memory

router=APIRouter(prefix='/semantic',tags=['Memoria semántica privada'])
MODEL='sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2'
_models={}
_lock=threading.Lock()
_inference=threading.Lock()

def model_path(settings):
    manifest=settings.data_dir/'models'/'semantic-model.json'
    try:
        info=json.loads(manifest.read_text())
        path=Path(info['path'])
        if not path.is_absolute(): path=settings.data_dir/'models'/path
        path=path.resolve()
        if info['model']!=MODEL or not path.is_relative_to((settings.data_dir/'models').resolve()) or not (path/'model_optimized.onnx').is_file(): return None
        return path
    except (OSError,ValueError,KeyError,TypeError): return None

def semantic_status(settings):
    ready=model_path(settings) is not None
    return {'available':ready,'engine':'fastembed-onnx-local' if ready else 'not_configured','model':MODEL,
        'dimensions':384,'private_context_forwarded':False,'query_downloads':False,'index_limit':800,
        'message_scope':'Solo mensajes aportados por su titular; respuestas del asistente excluidas'}

def embed(settings,texts):
    path=model_path(settings)
    if path is None: raise HTTPException(409,'El modelo semántico local no está preparado. Puedes seguir usando la búsqueda por texto')
    key=str(path)
    with _lock:
        if key not in _models:
            # This path bypasses FastEmbed's downloader entirely. Inference never uses Hub credentials.
            import onnxruntime
            onnxruntime.disable_telemetry_events()
            from fastembed import TextEmbedding
            _models[key]=TextEmbedding(MODEL,specific_model_path=key,local_files_only=True,threads=2,providers=['CPUExecutionProvider'])
    if not _inference.acquire(timeout=5):raise HTTPException(503,'La memoria semántica está ocupada. Inténtalo de nuevo en unos segundos')
    try:return [v.tolist() for v in _models[key].embed((t[:1600] for t in texts),batch_size=32,parallel=None)]
    finally:_inference.release()

def digest(text): return hashlib.sha256(text.encode()).hexdigest()

def candidates(db,user,day=None):
    memories=select(Memory).where(Memory.user_id==user.id)
    messages=select(Message).join(Conversation).where(Conversation.user_id==user.id,Message.role=='user')
    if day:
        start,end=day_bounds(day)
        memories=memories.where(or_((Memory.event_at>=start)&(Memory.event_at<end),(Memory.event_at.is_(None))&(Memory.created_at>=start)&(Memory.created_at<end)))
        messages=messages.where(Message.created_at>=start,Message.created_at<end)
    return [('memory',m) for m in db.scalars(memories.order_by(Memory.updated_at.desc()).limit(500))]+[('message',m) for m in db.scalars(messages.order_by(Message.created_at.desc()).limit(300))]

def index_memory(db,user,settings):
    if model_path(settings) is None:raise HTTPException(409,'El modelo semántico local no está preparado')
    rows=candidates(db,user)
    stored={(v.entity,v.record_id):v for v in db.scalars(select(SemanticVector).where(SemanticVector.user_id==user.id,SemanticVector.model==MODEL))}
    current={(entity,obj.id) for entity,obj in rows}
    for key,value in stored.items():
        if key not in current: db.delete(value)
    pending=[(entity,obj) for entity,obj in rows if (entity,obj.id) not in stored or stored[(entity,obj.id)].content_hash!=digest(obj.content)]
    if pending:
        vectors=embed(settings,[obj.content for _,obj in pending])
        for (entity,obj),vector in zip(pending,vectors,strict=True):
            row=stored.get((entity,obj.id))
            if row is None:
                row=SemanticVector(user_id=user.id,entity=entity,record_id=obj.id,model=MODEL);db.add(row)
            row.content_hash=digest(obj.content);row.vector=vector
    db.flush()
    # Relations are suggestions, never automatic merging or deletion.
    import numpy as np
    vectors=list(db.scalars(select(SemanticVector).where(SemanticVector.user_id==user.id,SemanticVector.entity=='memory',SemanticVector.model==MODEL)))
    db.execute(delete(MemoryRelation).where(MemoryRelation.user_id==user.id))
    if len(vectors)>1:
        matrix=np.asarray([v.vector for v in vectors]);norm=np.linalg.norm(matrix,axis=1,keepdims=True);matrix=matrix/np.maximum(norm,1e-12)
        scores=matrix@matrix.T
        added=0
        for i in range(len(vectors)):
            for j in range(i+1,len(vectors)):
                score=float(scores[i,j])
                if score>=.66 and added<300:
                    left,right=sorted([vectors[i].record_id,vectors[j].record_id])
                    db.add(MemoryRelation(user_id=user.id,left_id=left,right_id=right,confidence=round(score,5),
                        kind='possible_duplicate' if score>=.9 else 'related',provenance='Similitud coseno · '+MODEL));added+=1
    return {'indexed':len(rows),'updated':len(pending),'limit':800,'truncated':len(rows)>=800,'model':MODEL}

def search_semantic(db,user,args,settings):
    status=semantic_status(settings)
    if not status['available']:
        return {**retrieve_memory(db,user,args.query,args.day,args.limit),'semantic':status,'index_required':True}
    rows={(entity,obj.id):obj for entity,obj in candidates(db,user,args.day)}
    vectors=list(db.scalars(select(SemanticVector).where(SemanticVector.user_id==user.id,SemanticVector.model==MODEL)))
    # Apply ownership/date/deletion/correction checks BEFORE ranking; vectors alone grant no read access.
    valid=[v for v in vectors if (v.entity,v.record_id) in rows and v.content_hash==digest(rows[(v.entity,v.record_id)].content)]
    scored=[]
    if valid:
        import numpy as np
        query=np.asarray(embed(settings,[args.query])[0]);query=query/max(float(np.linalg.norm(query)),1e-12)
        for vector in valid:
            value=np.asarray(vector.vector);score=float(query@value/max(float(np.linalg.norm(value)),1e-12))
            if score>=.30: scored.append((score,vector.entity,rows[(vector.entity,vector.record_id)]))
    lexical=retrieve_memory(db,user,args.query,args.day,args.limit)
    by_key={(entity,obj.id):(score,entity,obj) for score,entity,obj in scored}
    for category,entity in [('memories','memory'),('messages','message')]:
        for match in lexical[category]:
            key=(entity,match['id'])
            if key in rows:
                score=by_key.get(key,(0,))[0];by_key[key]=(score+.15,entity,rows[key])
    annotations={a.memory_id:a for a in db.scalars(select(MemoryAnnotation).where(MemoryAnnotation.user_id==user.id))}
    out={'memories':[],'messages':[],'semantic':status,'index_required':len(valid)<len(rows)}
    for score,entity,obj in sorted(by_key.values(),key=lambda v:v[0],reverse=True)[:args.limit]:
        item=dict(record(obj),entity=entity,relevance=round(score,4))
        if entity=='memory': item['annotation']=record(annotations[obj.id]) if obj.id in annotations else {'state':'provisional','provenance':obj.source,'source_message_id':None}
        else: item['provenance']='Mensaje original de su titular'
        out['memories' if entity=='memory' else 'messages'].append(item)
    return out

@router.get('/status')
def status(request:Request,user=Depends(current_user),db=Depends(get_db)):
    return semantic_status(request.app.state.settings)

@router.post('/index')
def build_index(request:Request,user=Depends(current_user),db=Depends(get_db)):
    result=index_memory(db,user,request.app.state.settings);db.commit();return result

@router.post('/search')
def search(body:SemanticQuery,request:Request,user=Depends(current_user),db=Depends(get_db)):
    return search_semantic(db,user,body,request.app.state.settings)

@router.get('/relations')
def relations(user=Depends(current_user),db=Depends(get_db)):
    own=select(Memory.id).where(Memory.user_id==user.id)
    return [dict(record(r),left_content=db.get(Memory,r.left_id).content[:300],right_content=db.get(Memory,r.right_id).content[:300]) for r in db.scalars(select(MemoryRelation).where(MemoryRelation.user_id==user.id,MemoryRelation.left_id.in_(own),MemoryRelation.right_id.in_(own)).limit(300))]

@router.patch('/memories/{memory_id}')
def annotate(memory_id:str,body:AnnotationInput,user=Depends(current_user),db=Depends(get_db)):
    obj=db.scalar(select(Memory).where(Memory.id==memory_id,Memory.user_id==user.id))
    if not obj: raise HTTPException(404,'Recuerdo no disponible')
    annotation=db.scalar(select(MemoryAnnotation).where(MemoryAnnotation.memory_id==obj.id,MemoryAnnotation.user_id==user.id))
    if annotation is None: annotation=MemoryAnnotation(user_id=user.id,memory_id=obj.id);db.add(annotation)
    annotation.state=body.state;annotation.provenance='Confirmado por su titular; no es información institucional' if body.state=='confirmed' else 'Aportado por su titular; pendiente de comprobar'
    db.commit();return record(annotation)

def invalidate(db,user,memory_id):
    db.execute(delete(SemanticVector).where(SemanticVector.user_id==user.id,SemanticVector.entity=='memory',SemanticVector.record_id==memory_id))
    db.execute(delete(MemoryRelation).where(MemoryRelation.user_id==user.id,or_(MemoryRelation.left_id==memory_id,MemoryRelation.right_id==memory_id)))
