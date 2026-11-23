import hashlib
import secrets
from datetime import timedelta
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError, InvalidHashError
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select, func, delete
from .db import utcnow
from .models import User, Session, LoginAttempt, LearnerProfile, RemoteInvitation
from .schemas import Login, PreferencesInput, PasswordInput
from .policy import audit, group_ids

router = APIRouter(prefix='/auth', tags=['Autenticación'])
ph = PasswordHasher(time_cost=2, memory_cost=32768, parallelism=2)
DUMMY_HASH = ph.hash(secrets.token_urlsafe(32))
COOKIE = 'axon_session'


def get_db(request: Request):
    with request.app.state.session_factory() as db:
        try:
            yield db
        finally:
            db.rollback()


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def verify(password, hashed):
    try:
        return ph.verify(hashed, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def public_user(db, u):
    from .models import GuestSession,TeacherDemoSession
    guest=db.scalar(select(GuestSession).where(GuestSession.user_id==u.id)) if u.preferences.get('public_guest') else None
    teacher=db.scalar(select(TeacherDemoSession).where(TeacherDemoSession.user_id==u.id)) if u.preferences.get('demo_teacher') else None
    return {'demo_teacher':bool(teacher),'demo_expires_at':teacher.expires_at.isoformat() if teacher else None,'temporary_guest':bool(guest),'guest_expires_at':guest.expires_at.isoformat() if guest else None,'id': u.id, 'username': u.username, 'display_name': u.display_name, 'role': u.role,
            'has_academic_profile':bool(db.scalar(select(LearnerProfile.id).where(LearnerProfile.user_id==u.id))), 'is_demo': u.is_demo, 'center_id': u.center_id, 'group_ids': group_ids(db, u), 'preferences': u.preferences}


def current_user(request: Request, db=Depends(get_db)):
    token = request.cookies.get(COOKIE, '')
    session = db.scalar(select(Session).where(Session.token_hash == digest(token), Session.expires_at > utcnow())) if token else None
    user = db.get(User, session.user_id) if session else None
    if not user or not user.active:
        raise HTTPException(401, 'Inicia sesión para continuar')
    if request.app.state.settings.full_demo:
        from .teacher_demo import ensure
        ensure(db,user)
    elif request.app.state.settings.public_demo:
        from .guest import ensure_guest
        ensure_guest(db,user)
    if request.app.state.settings.remote_demo:
        binding=db.scalar(select(RemoteInvitation).where(RemoteInvitation.user_id==user.id))
        if not binding or binding.revoked or binding.email!=getattr(request.state,'access_email',''):raise HTTPException(403,'Esta sesión corresponde a otra identidad invitada')
    if request.method not in ('GET', 'HEAD', 'OPTIONS'):
        supplied = request.headers.get('x-csrf-token', '')
        if not secrets.compare_digest(supplied, session.csrf_token):
            raise HTTPException(403, 'La sesión necesita actualizarse. Recarga la página')
    if request.app.state.settings.full_demo:
        from .teacher_demo import request_limit,consume
        request_limit(db,user,request)
        if request.method in ('POST','PATCH','PUT') and (request.url.path in ('/api/tools/call','/api/math','/api/memory','/api/study/sessions','/api/documents','/api/voice/speech','/api/voice/transcribe','/api/semantic/index','/api/semantic/search','/api/research','/api/research/compare','/api/integrations/classroom/sync') or request.url.path.startswith('/api/study/sessions/') or (request.url.path.startswith('/api/classes/') and request.url.path.endswith('/assist'))):consume(db,user,request)
    if request.app.state.settings.public_demo and not request.app.state.settings.full_demo and request.method in ('POST','PATCH'):
        path=request.url.path
        if path in ('/api/tools/call','/api/math','/api/memory','/api/study/sessions') or path.startswith('/api/study/sessions/') or (path.startswith('/api/memory/') and request.method=='PATCH'):
            from .guest import consume_query
            consume_query(db,user,request)
    request.state.auth_session = session
    from .extensions import enforce_path
    enforce_path(request,user,db)
    return user


@router.post('/login')
def login(body: Login, request: Request, response: Response, db=Depends(get_db)):
    name = body.username.lower()
    ip = getattr(request.state,'access_email',None) or (request.client.host if request.client else 'local')
    key = digest(f'{ip}:{name}')
    network_key = digest(f'login-network:{ip}')
    recent = utcnow() - timedelta(minutes=10)
    for attempt_key, limit in ((key, 8), (network_key, 120)):
        attempts = db.scalar(select(func.count()).select_from(LoginAttempt).where(LoginAttempt.key_hash == attempt_key, LoginAttempt.created_at > recent))
        if attempts >= limit:
            raise HTTPException(429, 'Demasiados intentos. Espera diez minutos', headers={'Retry-After':'600'})
    user = db.scalar(select(User).where(User.username == name))
    good = verify(body.password, user.password_hash if user and user.active and user.password_hash else DUMMY_HASH)
    if not good or not user or not user.active:
        db.add_all([LoginAttempt(key_hash=key), LoginAttempt(key_hash=network_key)])
        db.commit()
        raise HTTPException(401, 'Usuario o contraseña incorrectos')
    if request.app.state.settings.remote_demo:
        binding=db.scalar(select(RemoteInvitation).where(RemoteInvitation.user_id==user.id,RemoteInvitation.revoked.is_(False),RemoteInvitation.consumed.is_(True)))
        if not binding or binding.email!=getattr(request.state,'access_email',''):raise HTTPException(403,'La cuenta no corresponde a esta identidad invitada')
    db.execute(delete(LoginAttempt).where(LoginAttempt.key_hash == key))
    if ph.check_needs_rehash(user.password_hash):
        user.password_hash = ph.hash(body.password)
    old = request.cookies.get(COOKIE)
    if old:
        db.execute(delete(Session).where(Session.token_hash == digest(old)))
    token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    expiry = utcnow() + timedelta(hours=request.app.state.settings.session_hours)
    db.add(Session(user_id=user.id, token_hash=digest(token), csrf_token=csrf, expires_at=expiry))
    db.commit()
    response.set_cookie(COOKIE, token, httponly=True, secure=request.app.state.settings.cookie_secure,
                        samesite='strict', max_age=request.app.state.settings.session_hours*3600, path='/')
    return {'user': public_user(db, user), 'csrf_token': csrf}


@router.get('/me')
def me(request: Request, user=Depends(current_user), db=Depends(get_db)):
    return {'user': public_user(db, user), 'csrf_token': request.state.auth_session.csrf_token}


@router.post('/logout')
def logout(request: Request, response: Response, user=Depends(current_user), db=Depends(get_db)):
    db.delete(request.state.auth_session)
    db.commit()
    response.delete_cookie(COOKIE, path='/')
    return {'ok': True}


@router.patch('/preferences')
def preferences(body: PreferencesInput, user=Depends(current_user), db=Depends(get_db)):
    user.preferences = {**user.preferences,**body.model_dump()}
    db.commit()
    return public_user(db, user)


@router.post('/password')
def password(body: PasswordInput, response: Response, user=Depends(current_user), db=Depends(get_db)):
    if not verify(body.current_password, user.password_hash):
        raise HTTPException(403, 'La contraseña actual no es correcta')
    user.password_hash = ph.hash(body.new_password)
    db.execute(delete(Session).where(Session.user_id == user.id))
    audit(db, user, 'password_changed', user)
    db.commit()
    response.delete_cookie(COOKIE, path='/')
    return {'ok': True, 'message': 'Contraseña actualizada. Vuelve a iniciar sesión'}
