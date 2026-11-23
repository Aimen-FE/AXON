"""Fail-closed invited demonstration, with an independent fictitious database."""
import asyncio,json,re,secrets,time
from pathlib import Path
from datetime import timedelta
from urllib.parse import urlsplit
import httpx,jwt
from fastapi import APIRouter,Depends,HTTPException,Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel,Field,ConfigDict
from sqlalchemy import select,delete,func,update
from .config import ROOT
from .auth import current_user,get_db,digest,ph
from .models import RemoteInvitation,User,Session,Center,LearnerProfile,KnowledgeSource,Document
from .policy import require_role,audit
from .db import utcnow
router=APIRouter(prefix='/remote',tags=['Demostración por invitación'])


def validate_profile(settings,db):
    """Remote never silently reuses the personal installation, or a default password."""
    if not settings.remote_demo:return
    if not settings.cookie_secure or settings.allowed_origins!=(f'https://{settings.public_hostname}',):raise ValueError('El perfil remoto exige cookies seguras y un único origen HTTPS exacto')
    if not re.fullmatch(r'(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}',settings.public_hostname):raise ValueError('Configura un nombre de dominio autorizado; no se generan dominios')
    if not re.fullmatch(r'https://[a-z0-9-]+\.cloudflareaccess\.com',settings.access_issuer) or not 16<=len(settings.access_audience)<=200:raise ValueError('Configura el emisor y la audiencia de Cloudflare Access')
    marker=settings.data_dir/'remote-demo.json'
    if settings.data_dir==ROOT/'data' or settings.data_dir.is_symlink() or not marker.is_file() or marker.is_symlink():raise ValueError('El perfil remoto requiere una carpeta ficticia independiente preparada por el operador')
    if not settings.database_url.startswith('sqlite'):raise ValueError('La demostración aislada usa SQLite local')
    from sqlalchemy.engine import make_url
    database=Path(make_url(settings.database_url).database).resolve()
    if database.parent!=settings.data_dir.resolve():raise ValueError('La base remota debe estar físicamente dentro de su carpeta independiente')
    info=json.loads(marker.read_text())
    if info.get('profile')!='atlas-fictitious-v1' or info.get('center_id')!=db.scalar(select(Center.id)):raise ValueError('El marcador no corresponde a esta base ficticia')
    if db.scalar(select(func.count()).select_from(User).where(User.is_demo.is_(False))):raise ValueError('Se detectaron cuentas o datos personales; el inicio remoto se ha bloqueado')
    for user in db.scalars(select(User)):
        if (user.active or user.password_hash) and not db.scalar(select(RemoteInvitation.id).where(RemoteInvitation.user_id==user.id,RemoteInvitation.consumed.is_(True),RemoteInvitation.revoked.is_(False))):raise ValueError('Hay una cuenta activa o con contraseña sin invitación individual')
    for doc in db.scalars(select(Document)):
        owner=db.get(User,doc.owner_id)
        path=settings.data_dir/'uploads'/doc.storage_key
        if not owner or not owner.is_demo or owner.center_id!=info['center_id'] or doc.center_id!=info['center_id'] or path.is_symlink() or not path.resolve().is_relative_to((settings.data_dir/'uploads').resolve()):raise ValueError('La demostración contiene archivos o propietarios ajenos a su perfil ficticio')

class AccessVerifier:
    def __init__(self,settings):self.settings=settings;self.keys={};self.loaded=0;self.lock=asyncio.Lock()
    async def verify(self,token):
        if not token or len(token)>8192:raise ValueError('Missing token')
        header=jwt.get_unverified_header(token);kid=header.get('kid')
        if header.get('alg')!='RS256' or not isinstance(kid,str) or len(kid)>200:raise ValueError('Invalid algorithm')
        now=time.monotonic()
        if now-self.loaded>300 or not self.loaded:
            async with self.lock:
                if time.monotonic()-self.loaded>300 or not self.loaded:
                    async with httpx.AsyncClient(timeout=4,trust_env=False) as client:
                        response=await client.get(self.settings.access_issuer+'/cdn-cgi/access/certs');response.raise_for_status()
                    if len(response.content)>100000:raise ValueError('Invalid key set')
                    self.keys={k['kid']:jwt.algorithms.RSAAlgorithm.from_jwk(json.dumps(k)) for k in response.json()['keys'][:10] if k.get('kty')=='RSA' and k.get('alg','RS256')=='RS256'};self.loaded=time.monotonic()
        if kid not in self.keys:raise ValueError('Unknown signing key')
        claims=jwt.decode(token,self.keys[kid],algorithms=['RS256'],issuer=self.settings.access_issuer,audience=self.settings.access_audience,options={'require':['exp','iat','iss','aud','sub','email']},leeway=5)
        email=claims.get('email')
        if not isinstance(email,str) or not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',email):raise ValueError('Invalid identity')
        return email.casefold()

async def guard(request,app):
    settings=app.state.settings
    if not settings.remote_demo:return None
    if (settings.pages_origin and request.method == 'GET' and request.url.path == '/api/public/connection'
        and request.headers.get('origin') == settings.pages_origin):
        return None
    try:
        email=await app.state.access_verifier.verify(request.headers.get('cf-access-jwt-assertion',''))
        with app.state.session_factory() as db:
            invite=db.scalar(select(RemoteInvitation).where(RemoteInvitation.email==email,RemoteInvitation.revoked.is_(False)))
            if not invite or (not invite.consumed and invite.expires_at<=utcnow()):raise ValueError('Not invited')
            request.state.access_email=email
    except (ValueError,KeyError,TypeError,jwt.PyJWTError,httpx.HTTPError):return JSONResponse({'detail':'Acceso externo no autorizado'},403)
    now=time.monotonic();bucket=app.state.remote_limits.setdefault(email,[])
    bucket[:]=[x for x in bucket if now-x[0]<60]
    uses_model = request.method == 'POST' and (request.url.path.endswith('/messages') or
        (request.url.path.startswith('/api/classes/') and request.url.path.endswith('/assist')))
    if len(bucket)>=120 or (uses_model and sum(x[1] for x in bucket)>=6):return JSONResponse({'detail':'Espera un minuto antes de continuar'},429,headers={'Retry-After':'60'})
    bucket.append((now,uses_model))
    return None

def require_remote(request):
    if not request.app.state.settings.remote_demo:raise HTTPException(404,'Las invitaciones están disponibles solo en la demostración aislada')

class InviteInput(BaseModel):
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
    user_id:str=Field(min_length=36,max_length=36)
    email:str=Field(min_length=5,max_length=254,pattern=r'^[^\s@]+@[^\s@]+\.[^\s@]+$')
    hours:int=Field(default=24,ge=1,le=72)

@router.get('/invitations')
def invitations(request:Request,user=Depends(current_user),db=Depends(get_db)):
    require_role(user,'admin');require_remote(request)
    return [{'user_id':i.user_id,'email':i.email,'expires_at':i.expires_at.isoformat(),'consumed':i.consumed,'revoked':i.revoked} for i in db.scalars(select(RemoteInvitation).join(User).where(User.center_id==user.center_id))]

def issue(db,target,email,hours):
    old=db.scalar(select(RemoteInvitation).where(RemoteInvitation.user_id==target.id))
    token=secrets.token_urlsafe(32)
    if old:
        old.email=email.casefold();old.token_hash=digest(token);old.expires_at=utcnow()+timedelta(hours=hours);old.consumed=False;old.revoked=False
    else:db.add(RemoteInvitation(user_id=target.id,email=email.casefold(),token_hash=digest(token),expires_at=utcnow()+timedelta(hours=hours)))
    target.active=False;target.password_hash='';db.execute(delete(Session).where(Session.user_id==target.id));db.flush();return token

@router.post('/invitations')
def invite(body:InviteInput,request:Request,user=Depends(current_user),db=Depends(get_db)):
    require_role(user,'admin');require_remote(request)
    target=db.get(User,body.user_id)
    if not target or target.center_id!=user.center_id or not target.is_demo or target.id==user.id:raise HTTPException(404,'Cuenta ficticia invitada no disponible')
    token=issue(db,target,body.email,body.hours);audit(db,user,'remote_invitation_issued',target,{'hours':body.hours});db.commit()
    return {'link':f'https://{request.app.state.settings.public_hostname}/#invite={token}','expires_hours':body.hours,'message':'Comparte el enlace de forma privada con su destinatario. AXON no envía correos.'}

class AcceptInput(BaseModel):
    model_config=ConfigDict(extra='forbid')
    token:str=Field(min_length=40,max_length=100)
    password:str=Field(min_length=12,max_length=128)

@router.post('/accept')
def accept(body:AcceptInput,request:Request,db=Depends(get_db)):
    require_remote(request)
    if not re.search(r'[a-zA-Z]',body.password) or not re.search(r'\d',body.password):raise HTTPException(422,'Usa al menos doce caracteres con letras y números')
    invite=db.scalar(select(RemoteInvitation).where(RemoteInvitation.token_hash==digest(body.token),RemoteInvitation.email==getattr(request.state,'access_email',''),RemoteInvitation.consumed.is_(False),RemoteInvitation.revoked.is_(False),RemoteInvitation.expires_at>utcnow()))
    if not invite:raise HTTPException(403,'La invitación no es válida, ha caducado o corresponde a otra identidad')
    changed=db.execute(update(RemoteInvitation).where(RemoteInvitation.id==invite.id,RemoteInvitation.consumed.is_(False),RemoteInvitation.revoked.is_(False)).values(consumed=True)).rowcount
    if changed!=1:raise HTTPException(409,'La invitación ya se ha utilizado')
    user=db.get(User,invite.user_id);user.password_hash=ph.hash(body.password);user.active=True
    audit(db,user,'remote_invitation_accepted',user);db.commit()
    return {'username':user.username,'message':'Cuenta activada. Inicia sesión con tu contraseña individual.'}

@router.post('/revoke/{user_id}')
def revoke(user_id:str,request:Request,user=Depends(current_user),db=Depends(get_db)):
    require_role(user,'admin');require_remote(request)
    target=db.get(User,user_id);invite=db.scalar(select(RemoteInvitation).where(RemoteInvitation.user_id==user_id))
    if not target or target.center_id!=user.center_id or not invite or user_id==user.id:raise HTTPException(404,'Invitación no disponible')
    target.active=False;target.password_hash='';invite.revoked=True;db.execute(delete(Session).where(Session.user_id==user_id));audit(db,user,'remote_access_revoked',target);db.commit();return {'revoked':True}

@router.get('/readiness')
def readiness(request:Request,user=Depends(current_user)):
    require_role(user,'admin');s=request.app.state.settings;folder=ROOT/'data'/'atlas-demo'
    return {'remote_profile':s.remote_demo,'fictitious_database_prepared':(folder/'remote-demo.json').is_file(),'connector_installed':(ROOT/'data/tools/cloudflared').is_file(),'hostname_configured':bool(s.public_hostname),'access_configured':bool(s.access_issuer and s.access_audience),'secure_cookies':s.cookie_secure,'publication':'AXON no crea ni inicia túneles. La publicación y la prueba desde otro dispositivo requieren autorización y configuración externas.','pending':['Configurar o verificar Access en la cuenta Cloudflare','Dominio o alternativa autorizada compatible con Access','Cuenta y aplicación Access, audiencia y política de correos invitados','Correos individuales del operador y los tres docentes','Autorización explícita de publicación y prueba desde otro dispositivo'] if not s.remote_demo else ['Verificar túnel, DNS y política Access en la cuenta real','Prueba externa autorizada']}
