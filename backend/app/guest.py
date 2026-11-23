"""Public, fictional and short-lived demo. Explicit routes and tools only."""
import hashlib,hmac,ipaddress,json,re,secrets
from datetime import timedelta
from pathlib import Path
from fastapi import APIRouter,Depends,HTTPException,Request,Response
from fastapi.responses import JSONResponse
from sqlalchemy import select,func,delete,update
from .auth import current_user,get_db,COOKIE,digest,public_user
from .models import User,Session,GuestSession,GuestRate,Center,Group,Enrollment,Document,Conversation,Memory,Message
from .db import utcnow
from .config import ROOT
router=APIRouter(prefix='/guest',tags=['Sesión temporal de demostración'])
MAX_REQUESTS=20
SAFE_TOOLS={'query_exams','query_calendar','query_schedule','query_assignments','query_subjects','search_memory','search_documents','save_memory','get_study_context','get_school_information','get_my_schedule','get_subjects','get_teachers','query_knowledge','calculate_math','calculate_grade','get_notifications','get_pending'}
GET_EXACT={'/api/public/connection','/api/auth/me','/api/system','/api/public/info','/api/guest/status','/api/academic','/api/dashboard','/api/events','/api/assignments','/api/schedules','/api/notifications','/api/actions','/api/tools','/api/memory','/api/atlas/core','/api/atlas/sources','/api/atlas/layers','/api/documents','/api/documents/search','/api/study/sessions','/api/study/plans','/api/personal-tasks','/api/agent/runs','/api/learner','/api/knowledge','/api/knowledge/progress'}
GET_PATTERNS=(r'/api/conversations(?:/[a-f0-9-]{36})?',r'/api/documents/[a-f0-9-]{36}/(?:chunks|download)',r'/api/events/[a-f0-9-]{36}',r'/api/agent/runs/[a-f0-9-]{36}')
WRITE_PATTERNS=(r'/api/conversations',r'/api/conversations/[a-f0-9-]{36}/messages',r'/api/conversations/[a-f0-9-]{36}/cancel/[\w-]{1,80}',r'/api/memory',r'/api/memory/[a-f0-9-]{36}',r'/api/study/sessions',r'/api/study/sessions/[a-f0-9-]{36}/answers',r'/api/tools/call',r'/api/guest/start',r'/api/guest/end',r'/api/math',r'/api/agent/runs/[a-f0-9-]{36}/cancel')
STATIC={'/','/index.html','/icon.svg','/icon-192.png','/icon-512.png','/icon-maskable-512.png','/apple-touch-icon.png','/manifest.webmanifest','/sw.js','/offline.html','/public-view.js','/public-view.css','/kiosk.html'}

def runtime(settings):
    path=settings.data_dir/'quick-runtime.json'
    if not path.is_file() or path.is_symlink() or path.stat().st_size>8192:return {}
    try:return json.loads(path.read_text())
    except (ValueError,OSError):return {}

def validate_profile(settings,db):
    if not settings.public_demo:return
    if settings.remote_demo or settings.data_dir.resolve()==(ROOT/'data').resolve() or not settings.cookie_secure:raise ValueError('La demo pública exige una carpeta ficticia independiente y cookies seguras')
    marker=settings.data_dir/'remote-demo.json'
    if not marker.is_file() or marker.is_symlink():raise ValueError('Falta el marcador de la base ficticia')
    from sqlalchemy.engine import make_url
    if not settings.database_url.startswith('sqlite') or Path(make_url(settings.database_url).database).resolve().parent!=settings.data_dir.resolve():raise ValueError('La base pública debe estar físicamente en su carpeta independiente')
    if json.loads(marker.read_text()).get('center_id')!=db.scalar(select(Center.id)):raise ValueError('Marcador de demostración no válido')
    if not re.fullmatch(r'axon-[a-f0-9]{64}\.localhost',settings.public_origin_host):raise ValueError('Falta la protección local del origen')
    for user in db.scalars(select(User)):
        if not user.is_demo:raise ValueError('La demostración contiene una cuenta personal')
        if user.active and not db.scalar(select(GuestSession.id).where(GuestSession.user_id==user.id)):raise ValueError('Una cuenta permanente está activa en el perfil público')
        if user.password_hash:raise ValueError('La demostración pública no utiliza contraseñas de cuentas permanentes')
    for doc in db.scalars(select(Document)):
        owner=db.get(User,doc.owner_id);file=settings.data_dir/'uploads'/doc.storage_key
        if not owner or not owner.is_demo or owner.center_id!=doc.center_id or file.is_symlink() or not file.resolve().is_relative_to((settings.data_dir/'uploads').resolve()):raise ValueError('Documento fuera del ámbito ficticio')

def is_guest(user):return bool(user.preferences.get('public_guest'))
def ensure_guest(db,user):
    obj=db.scalar(select(GuestSession).where(GuestSession.user_id==user.id,GuestSession.revoked.is_(False),GuestSession.expires_at>utcnow()))
    if not obj or user.role!='student' or not user.is_demo or not is_guest(user):raise HTTPException(401,'Tu sesión temporal ha terminado. Puedes comenzar una nueva si hay capacidad')
    return obj

def rate(db,key,limit,seconds,record=True):
    now=utcnow();count=db.scalar(select(func.count()).select_from(GuestRate).where(GuestRate.key_hash==key,GuestRate.created_at>now-timedelta(seconds=seconds)))
    if count>=limit:raise HTTPException(429,'Has alcanzado el límite temporal de la demostración. Inténtalo más tarde',headers={'Retry-After':str(seconds)})
    if record:db.add(GuestRate(key_hash=key));db.flush()

def ip_hash(request):
    # Accepted only after the private Host guard and loopback peer check.
    value=request.headers.get('cf-connecting-ip') or 'local'
    try:value=str(ipaddress.ip_address(value))
    except ValueError:value='local'
    secret=request.app.state.settings.public_origin_host.encode()
    return hmac.new(secret,value.encode(),hashlib.sha256).hexdigest()

async def guard(request,app):
    settings=app.state.settings
    if not settings.public_demo:return None
    if not request.client or request.client.host not in ('127.0.0.1','::1','testclient','testserver') or not secrets.compare_digest(request.headers.get('host','').split(':')[0],settings.public_origin_host):return JSONResponse({'detail':'Origen no disponible'},403,headers={'Cache-Control':'no-store'})
    state=runtime(settings);host=state.get('hostname','')
    if not state.get('enabled') or not re.fullmatch(r'[a-z0-9-]+\.trycloudflare\.com',host):return JSONResponse({'detail':'La demostración se está preparando'},503,headers={'Cache-Control':'no-store'})
    request.state.public_origin='https://'+host
    path=request.url.path;method=request.method
    allowed=(path in STATIC and method in ('GET','HEAD')) or ((path.startswith('/assets/') or path.startswith('/fonts/')) and method in ('GET','HEAD'))
    if path.startswith('/api/'):
        allowed=(method in ('GET','HEAD') and (path in GET_EXACT or any(re.fullmatch(p,path) for p in GET_PATTERNS))) or (method in ('POST','PATCH','DELETE') and any(re.fullmatch(p,path) for p in WRITE_PATTERNS))
    if not allowed:return JSONResponse({'detail':'Esta función no está disponible en la demostración pública'},403,headers={'Cache-Control':'no-store'})
    if method not in ('GET','HEAD','OPTIONS') and request.headers.get('origin')!=request.state.public_origin:return JSONResponse({'detail':'Origen de petición no autorizado'},403,headers={'Cache-Control':'no-store'})
    if path.startswith('/api/'):
        try:
            with app.state.session_factory() as db:
                rate(db,digest('http:'+ip_hash(request)),90,60)
                rate(db,digest('http-global'),240,60);db.commit()
        except HTTPException as exc:return JSONResponse({'detail':exc.detail},exc.status_code,headers={**(exc.headers or {}),'Cache-Control':'no-store'})
    return None

def consume_query(db,user,request):
    if not request.app.state.settings.public_demo:return
    if request.app.state.settings.full_demo:
        from .teacher_demo import consume
        return consume(db,user,request)
    obj=ensure_guest(db,user)
    rate(db,digest('chat-ip:'+ip_hash(request)),8,60)
    changed=db.execute(update(GuestSession).where(GuestSession.id==obj.id,GuestSession.request_count<MAX_REQUESTS).values(request_count=GuestSession.request_count+1,last_seen_at=utcnow())).rowcount
    if not changed:raise HTTPException(429,'Has utilizado las veinte consultas de esta sesión temporal')
    db.commit()

@router.post('/start')
def start(request:Request,response:Response,db=Depends(get_db)):
    if not request.app.state.settings.public_demo:raise HTTPException(404,'La sesión temporal está disponible solo en la demo pública')
    if db.bind.dialect.name=='sqlite':
        from sqlalchemy import text
        db.execute(text('BEGIN IMMEDIATE'))
    key=ip_hash(request);now=utcnow()
    rate(db,digest('new-guest:'+key),3,3600)
    rate(db,digest('new-guest-global'),120,3600)
    active=db.scalar(select(func.count()).select_from(GuestSession).where(GuestSession.expires_at>now,GuestSession.revoked.is_(False)))
    if active>=60:raise HTTPException(429,'La demostración está completa. Vuelve a intentarlo más tarde')
    center=db.scalar(select(Center));group=db.scalar(select(Group).where(Group.center_id==center.id).order_by(Group.name))
    expires=now+timedelta(hours=1);user=User(center_id=center.id,username='guest.'+secrets.token_hex(16),display_name='Invitado temporal',password_hash='',role='student',is_demo=True,active=True,preferences={'public_guest':True,'automatic_personal_actions':False})
    db.add(user);db.flush();db.add(Enrollment(user_id=user.id,group_id=group.id));db.add(GuestSession(user_id=user.id,ip_hash=key,expires_at=expires,last_seen_at=now))
    token,csrf=secrets.token_urlsafe(32),secrets.token_urlsafe(32);db.add(Session(user_id=user.id,token_hash=digest(token),csrf_token=csrf,expires_at=expires));db.commit()
    response.set_cookie(COOKIE,token,httponly=True,secure=True,samesite='strict',max_age=3600,path='/')
    return {'user':public_user(db,user),'csrf_token':csrf,'expires_at':expires.isoformat(),'remaining':MAX_REQUESTS}

@router.get('/status')
def status(user=Depends(current_user),db=Depends(get_db)):
    obj=ensure_guest(db,user);return {'expires_at':obj.expires_at.isoformat(),'remaining':max(0,MAX_REQUESTS-obj.request_count),'temporary':True}

def cleanup(db):
    expired=list(db.scalars(select(GuestSession).where((GuestSession.expires_at<=utcnow()) | GuestSession.revoked.is_(True)).limit(100)))
    for obj in expired:
        user=db.get(User,obj.user_id)
        if not user or not is_guest(user) or user.role!='student' or not user.is_demo:continue
        # Guest routes/tools cannot create institutional ownership; keep that invariant.
        if db.scalar(select(Document.id).where(Document.owner_id==user.id)):raise ValueError('Un invitado tiene documentos persistentes fuera de su alcance')
        db.execute(delete(User).where(User.id==user.id))
    db.execute(delete(GuestRate).where(GuestRate.created_at<utcnow()-timedelta(hours=1)))
    db.commit()

@router.post('/end')
async def end(request:Request,response:Response,user=Depends(current_user),db=Depends(get_db)):
    obj=ensure_guest(db,user)
    for owner,convo,ident,task in list(request.app.state.active_generations.values()):
        if owner==user.id:task.cancel()
    obj.revoked=True;db.commit();cleanup(db)
    response.delete_cookie(COOKIE,path='/');return {'ok':True,'temporary_data_deleted':True}
