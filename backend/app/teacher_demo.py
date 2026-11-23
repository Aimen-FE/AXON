"""The full AXON teacher UI, on separate fictitious school namespaces."""
import asyncio,json,re,secrets
from datetime import timedelta
from pathlib import Path
from fastapi import APIRouter,Depends,HTTPException,Request,Response
from fastapi.responses import JSONResponse
from sqlalchemy import select,func,update,delete,text
from .config import ROOT
from .db import utcnow
from .models import User,Session,Center,Document,TeacherDemoSession,GuestRate
from .auth import current_user,get_db,COOKIE,digest,public_user
from .guest import runtime,ip_hash,rate,STATIC
from . import demo_tenants

router=APIRouter(prefix='/teacher-demo',tags=['Profesor de demostración aislado'])
SESSION_HOURS=24
MAX_ACTIVE=40
QUERIES_PER_HOUR=100
DENIED=('/api/admin','/api/demo-launch','/api/teacher-launch','/api/remote','/api/operations','/api/profile/data','/api/auth/password','/api/account','/api/auth/login','/api/auth/logout','/api/guest','/api/ai/public-prompt','/api/integrations/classroom/authorize','/api/integrations/classroom/callback')


def marker(settings):
    path=settings.data_dir/'remote-demo.json'
    if not path.is_file() or path.is_symlink() or path.stat().st_size>8192:raise ValueError('Falta el marcador de la instancia ficticia de profesor')
    result=json.loads(path.read_text())
    if result.get('profile')!='teacher-fictitious-v1' or not result.get('personal_data_copied') is False:raise ValueError('La instancia no está identificada como ficticia')
    return result


def validate_profile(settings,db):
    if not settings.full_demo:return
    from sqlalchemy.engine import make_url
    if not settings.public_demo or settings.remote_demo or not settings.cookie_secure or settings.data_dir.resolve()==(ROOT/'data').resolve():raise ValueError('La publicación de profesor exige una base ficticia independiente')
    if not settings.database_url.startswith('sqlite') or Path(make_url(settings.database_url).database).resolve().parent!=settings.data_dir.resolve():raise ValueError('La base debe estar dentro de su carpeta ficticia')
    if not re.fullmatch(r'axon-[a-f0-9]{64}\.localhost',settings.public_origin_host):raise ValueError('Falta la protección del origen')
    data=marker(settings);base=db.get(Center,data['center_id'])
    if not base:raise ValueError('No existe la plantilla de demostración')
    sessions=list(db.scalars(select(TeacherDemoSession)));centers={s.center_id for s in sessions};teachers={s.user_id:s.center_id for s in sessions}
    if set(db.scalars(select(Center.id)))-centers-{base.id}:raise ValueError('Existe un centro ajeno a las sesiones ficticias')
    for user in db.scalars(select(User)):
        if not user.is_demo or user.password_hash:raise ValueError('Una cuenta personal o con contraseña está presente en la demostración')
        if not user.active:continue
        allowed=(user.id in teachers and user.role in ('teacher','student','admin') and user.preferences.get('demo_teacher') and teachers[user.id]==user.center_id) or (user.center_id in centers and user.role in ('student','teacher','admin') and user.preferences.get('demo_roster'))
        if not allowed:raise ValueError('Una cuenta permanente está activa fuera del ámbito de demostración')
    for doc in db.scalars(select(Document)):
        owner=db.get(User,doc.owner_id);path=settings.data_dir/'uploads'/doc.storage_key
        if not owner or not owner.is_demo or owner.center_id!=doc.center_id or path.is_symlink() or not path.resolve().is_relative_to((settings.data_dir/'uploads').resolve()):raise ValueError('Archivo fuera del ámbito ficticio')


def ensure(db,user):
    row=db.scalar(select(TeacherDemoSession).where(TeacherDemoSession.user_id==user.id,TeacherDemoSession.center_id==user.center_id,TeacherDemoSession.revoked.is_(False),TeacherDemoSession.expires_at>utcnow()))
    if not row or user.role not in ('teacher','student','admin') or not user.is_demo or not user.preferences.get('demo_teacher'):raise HTTPException(401,'Tu sesión de profesor ha terminado. Puedes abrir otra sin contraseña')
    return row


def _http_limit(app,request):
    with app.state.session_factory() as db:
        rate(db,digest('teacher-http-ip:'+ip_hash(request)),1200,60)
        rate(db,digest('teacher-http-total'),1800,60);db.commit()


async def guard(request,app):
    settings=app.state.settings
    if not settings.full_demo:return None
    peer=request.client.host if request.client else ''
    if peer not in ('127.0.0.1','::1','testclient','testserver') or not secrets.compare_digest(request.headers.get('host','').split(':')[0],settings.public_origin_host):return JSONResponse({'detail':'Origen no disponible'},403,headers={'Cache-Control':'no-store'})
    state=runtime(settings);host=state.get('hostname','')
    if not state.get('enabled') or not re.fullmatch(r'[a-z0-9-]+\.trycloudflare\.com',host):return JSONResponse({'detail':'La publicación se está preparando'},503,headers={'Cache-Control':'no-store'})
    request.state.public_origin='https://'+host;path=request.url.path
    is_api=path.startswith('/api/')
    allowed=(request.method in ('GET','HEAD') and (path in STATIC or path.startswith('/assets/') or path.startswith('/fonts/'))) or is_api
    admin_education = path in ('/api/admin/users','/api/admin/groups','/api/admin/teaching','/api/admin/structure','/api/admin/enrollments') or bool(re.fullmatch(r'/api/admin/users/[a-f0-9-]{36}', path))
    if path in ('/api/docs','/api/openapi.json') or (not admin_education and any(path==p or path.startswith(p+'/') for p in DENIED)):allowed=False
    if not allowed:return JSONResponse({'detail':'Esta operación no está permitida en la cuenta de profesor de demostración'},403,headers={'Cache-Control':'no-store'})
    if request.method not in ('GET','HEAD','OPTIONS') and request.headers.get('origin')!=request.state.public_origin:return JSONResponse({'detail':'Origen de petición no autorizado'},403,headers={'Cache-Control':'no-store'})
    if is_api:
        try:await asyncio.to_thread(_http_limit,app,request)
        except HTTPException as exc:return JSONResponse({'detail':exc.detail},exc.status_code,headers={**(exc.headers or {}),'Cache-Control':'no-store'})
    return None


def request_limit(db,user,request):
    session=ensure(db,user)
    rate(db,digest('teacher-session-http:'+session.id),300,60)
    if request.method not in ('GET','HEAD','OPTIONS'):rate(db,digest('teacher-session-writes:'+session.id),40,60)
    if session.last_seen_at<utcnow()-timedelta(minutes=1):session.last_seen_at=utcnow()
    db.commit()


def consume(db,user,request):
    row=ensure(db,user)
    rate(db,digest('teacher-query-minute:'+row.id),12,60)
    rate(db,digest('teacher-query-hour:'+row.id),QUERIES_PER_HOUR,3600)
    db.execute(update(TeacherDemoSession).where(TeacherDemoSession.id==row.id).values(request_count=TeacherDemoSession.request_count+1,last_seen_at=utcnow()));db.commit()


def upload_limit(db,user,size):
    count,total=db.execute(select(func.count(),func.coalesce(func.sum(Document.size),0)).where(Document.center_id==user.center_id)).one()
    if count>=1200 or total+size>100*1024**2:raise HTTPException(429,'Tu espacio ficticio admite hasta 1200 documentos y 100 MB. Elimina un documento propio para continuar')


from typing import Literal
from .schemas import Input

class DemoPerspective(Input):
    role: Literal['student','teacher','admin'] = 'teacher'

@router.post('/start')
def start(request:Request,response:Response,body:DemoPerspective=DemoPerspective(),db=Depends(get_db)):
    settings=request.app.state.settings
    if not settings.full_demo:raise HTTPException(404,'Esta entrada solo está disponible en la instancia de profesor')
    if db.bind.dialect.name=='sqlite':db.execute(text('BEGIN IMMEDIATE'))
    token=request.cookies.get(COOKIE,'')
    old=db.scalar(select(Session).where(Session.token_hash==digest(token),Session.expires_at>utcnow())) if token else None
    if old:
        user=db.get(User,old.user_id)
        if user and user.preferences.get('demo_teacher'):
            row=ensure(db,user);return {'user':public_user(db,user),'csrf_token':old.csrf_token,'expires_at':row.expires_at.isoformat()}
    now=utcnow();rate(db,digest('teacher-new-ip:'+ip_hash(request)),300,3600);rate(db,digest('teacher-new-total'),300,3600)
    active=db.scalar(select(func.count()).select_from(TeacherDemoSession).where(TeacherDemoSession.expires_at>now,TeacherDemoSession.revoked.is_(False)))
    if active>=MAX_ACTIVE:raise HTTPException(429,'Las cuarenta sesiones de profesor están ocupadas; prueba más tarde')
    user,center_id,files=demo_tenants.clone(db,settings,marker(settings)['center_id'],body.role)
    try:
        expires=now+timedelta(hours=SESSION_HOURS);db.add(TeacherDemoSession(user_id=user.id,center_id=center_id,expires_at=expires,last_seen_at=now))
        token,csrf=secrets.token_urlsafe(32),secrets.token_urlsafe(32);db.add(Session(user_id=user.id,token_hash=digest(token),csrf_token=csrf,expires_at=expires));db.commit()
    except Exception:
        db.rollback()
        for path in files:path.unlink(missing_ok=True)
        raise
    response.set_cookie(COOKIE,token,httponly=True,secure=True,samesite='strict',max_age=SESSION_HOURS*3600,path='/')
    return {'user':public_user(db,user),'csrf_token':csrf,'expires_at':expires.isoformat()}


@router.post('/perspective')
def change_perspective(body:DemoPerspective,request:Request,response:Response,user=Depends(current_user),db=Depends(get_db)):
    row=ensure(db,user)
    identity={'student':'alumno.demo','teacher':'profesor.demo','admin':'admin.demo'}[body.role]
    candidates=list(db.scalars(select(User).where(User.center_id==user.center_id)))
    target=next((person for person in candidates if person.preferences.get('demo_identity')==identity),None)
    if not target or not target.is_demo or target.password_hash:
        raise HTTPException(409,'El perfil ficticio no está disponible')
    from sqlalchemy import delete
    db.execute(delete(Session).where(Session.user_id==user.id))
    target.active=True
    target.preferences={**target.preferences,'demo_teacher':True}
    row.user_id=target.id
    token,csrf=secrets.token_urlsafe(32),secrets.token_urlsafe(32)
    db.add(Session(user_id=target.id,token_hash=digest(token),csrf_token=csrf,expires_at=row.expires_at))
    db.commit()
    response.set_cookie(COOKIE,token,httponly=True,secure=True,samesite='strict',max_age=SESSION_HOURS*3600,path='/')
    return {'user':public_user(db,target),'csrf_token':csrf}


@router.get('/status')
def status(user=Depends(current_user),db=Depends(get_db)):
    row=ensure(db,user);recent=db.scalar(select(func.count()).select_from(GuestRate).where(GuestRate.key_hash==digest('teacher-query-hour:'+row.id),GuestRate.created_at>utcnow()-timedelta(hours=1)))
    return {'role':user.role,'expires_at':row.expires_at.isoformat(),'queries_remaining_this_hour':max(0,QUERIES_PER_HOUR-recent),'isolated_school':True,'tunnel_has_session_time_limit':False}


def cleanup(db,settings,all_sessions=False):
    stmt=select(TeacherDemoSession)
    if not all_sessions:stmt=stmt.where((TeacherDemoSession.expires_at<=utcnow()) | TeacherDemoSession.revoked.is_(True)).limit(5)
    centers=list(db.scalars(stmt.with_only_columns(TeacherDemoSession.center_id)));template=marker(settings)['center_id']
    for center in centers:demo_tenants.remove(db,settings,center,template)
    db.execute(delete(GuestRate).where(GuestRate.created_at<utcnow()-timedelta(hours=1)));db.commit()


@router.post('/end')
async def end(request:Request,response:Response,user=Depends(current_user),db=Depends(get_db)):
    row=ensure(db,user);row.revoked=True;db.commit()
    for owner,convo,ident,task in list(request.app.state.active_generations.values()):
        if owner==user.id:task.cancel()
    demo_tenants.remove(db,request.app.state.settings,user.center_id,marker(request.app.state.settings)['center_id'])
    response.delete_cookie(COOKIE,path='/');return {'ok':True,'temporary_data_deleted':True}
