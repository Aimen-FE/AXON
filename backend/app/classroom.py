"""Conector oficial de solo lectura. No se inicia OAuth ni sincronización sin pulsación del titular."""
import base64,hashlib,json,os,secrets,time
from datetime import timedelta,datetime,timezone
from urllib.parse import urlencode,quote
import httpx
from cryptography.fernet import Fernet,InvalidToken
from fastapi import APIRouter,Depends,HTTPException,Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select,update,delete
from .auth import current_user,get_db,digest
from .db import utcnow
from .models import IntegrationConnection,OAuthAttempt,User,PersonalTask,IntegrationSync
from .learning_schemas import SyncInput
from .serializers import record
from .memory import MADRID

router=APIRouter(prefix='/integrations/classroom',tags=['Google Classroom de solo lectura'])
SCOPES=['https://www.googleapis.com/auth/classroom.courses.readonly','https://www.googleapis.com/auth/classroom.coursework.me.readonly','https://www.googleapis.com/auth/classroom.courseworkmaterials.readonly']
CALLBACK='http://127.0.0.1:8000/api/integrations/classroom/callback'


def config():return os.getenv('AXON_GOOGLE_CLIENT_ID',''),os.getenv('AXON_GOOGLE_CLIENT_SECRET','')

def cipher(settings):
    from .operations import storage_lock
    with storage_lock(settings):return _cipher(settings)

def _cipher(settings):
    folder=settings.data_dir/'secrets';folder.mkdir(mode=0o700,exist_ok=True);path=folder/'integrations.key'
    if not path.exists():
        try:
            fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
            with os.fdopen(fd,'wb') as stream:stream.write(Fernet.generate_key())
        except FileExistsError:pass
    return Fernet(path.read_bytes())

def encode(settings,payload):return cipher(settings).encrypt(json.dumps(payload).encode()).decode()
def decode(settings,blob):
    try:return json.loads(cipher(settings).decrypt(blob.encode()))
    except (InvalidToken,ValueError):raise HTTPException(503,'No se pueden recuperar las credenciales protegidas; vuelve a autorizar la conexión')

def connection(db,user):
    return db.scalar(select(IntegrationConnection).where(IntegrationConnection.user_id==user.id,IntegrationConnection.provider=='classroom'))

def public_connection(row):
    return record(row,('encrypted_payload',)) if row else {'status':'disconnected','mode':'unconfigured','last_sync':None,'last_error':''}


@router.get('')
def status(user=Depends(current_user),db=Depends(get_db)):
    client_id,secret=config()
    return {'configured':bool(client_id and secret),'connection':public_connection(connection(db,user)),'scopes':SCOPES,
            'real_connection_verified':False,'note':'La conexión real requiere tu autorización y una configuración OAuth institucional válida.'}


@router.post('/authorize')
def authorize(request:Request,user=Depends(current_user),db=Depends(get_db)):
    client_id,secret=config()
    if not client_id or not secret:raise HTTPException(409,'Google Classroom no está configurado: faltan las credenciales OAuth del proyecto. No se ha accedido a ninguna cuenta')
    state=secrets.token_urlsafe(40);verifier=secrets.token_urlsafe(64)
    challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()
    db.add(OAuthAttempt(user_id=user.id,state_hash=digest(state),encrypted_verifier=encode(request.app.state.settings,{'verifier':verifier}),expires_at=utcnow()+timedelta(minutes=10)))
    db.commit()
    return {'authorization_url':'https://accounts.google.com/o/oauth2/v2/auth?'+urlencode({'client_id':client_id,'redirect_uri':CALLBACK,'response_type':'code','scope':' '.join(SCOPES),'state':state,'access_type':'offline','prompt':'consent','code_challenge':challenge,'code_challenge_method':'S256'}),'read_only':True}


@router.get('/callback')
def callback(request:Request,state:str='',code:str='',error:str='',db=Depends(get_db)):
    if len(state)>200 or len(code)>2000:raise HTTPException(422,'Respuesta OAuth inválida')
    attempt=db.scalar(select(OAuthAttempt).where(OAuthAttempt.state_hash==digest(state),OAuthAttempt.used.is_(False),OAuthAttempt.expires_at>utcnow()))
    if not attempt:raise HTTPException(403,'La autorización no corresponde a una solicitud vigente')
    changed=db.execute(update(OAuthAttempt).where(OAuthAttempt.id==attempt.id,OAuthAttempt.used.is_(False)).values(used=True)).rowcount
    if not changed:raise HTTPException(409,'La autorización ya se ha utilizado')
    user=db.get(User,attempt.user_id)
    if not user or not user.active:raise HTTPException(403,'La cuenta ya no está activa')
    from .extensions import require_module
    require_module(db,user,'classroom')
    db.commit()  # Consume the one-time state even when the provider refuses permissions.
    if error or not code:return RedirectResponse('/#integrations',status_code=303)
    client_id,secret=config();verifier=decode(request.app.state.settings,attempt.encrypted_verifier)['verifier']
    try:
        with httpx.Client(timeout=15,trust_env=False) as client:
            response=client.post('https://oauth2.googleapis.com/token',data={'code':code,'client_id':client_id,'client_secret':secret,'redirect_uri':CALLBACK,'grant_type':'authorization_code','code_verifier':verifier})
            response.raise_for_status();tokens=response.json()
        if not tokens.get('access_token') or not set(SCOPES).issubset(set(tokens.get('scope','').split())):raise HTTPException(403,'No se concedieron los permisos mínimos de solo lectura')
        row=connection(db,user)
        if not row:row=IntegrationConnection(user_id=user.id,provider='classroom');db.add(row)
        row.encrypted_payload=encode(request.app.state.settings,tokens);row.mode='real';row.status='connected';row.last_error='';row.expires_at=utcnow()+timedelta(seconds=int(tokens.get('expires_in',3600)))
        db.commit();return RedirectResponse('/#integrations',status_code=303)
    except (httpx.HTTPError,ValueError,KeyError):
        db.commit();raise HTTPException(502,'Google no ha completado la autorización. No se ha anunciado una conexión válida')


def access_token(db,user,settings):
    row=connection(db,user)
    if not row or row.mode!='real' or row.status!='connected':raise HTTPException(409,'No hay una conexión real autorizada de Google Classroom')
    tokens=decode(settings,row.encrypted_payload)
    if row.expires_at and row.expires_at>utcnow()+timedelta(seconds=60):return tokens['access_token']
    if not tokens.get('refresh_token'):raise HTTPException(401,'La autorización ha caducado; vuelve a conectar Classroom')
    client_id,secret=config()
    try:
        with httpx.Client(timeout=15,trust_env=False) as client:
            response=client.post('https://oauth2.googleapis.com/token',data={'client_id':client_id,'client_secret':secret,'refresh_token':tokens['refresh_token'],'grant_type':'refresh_token'})
            response.raise_for_status();new=response.json();tokens.update(new)
        row.encrypted_payload=encode(settings,tokens);row.expires_at=utcnow()+timedelta(seconds=int(new.get('expires_in',3600)));db.commit()
        return tokens['access_token']
    except (httpx.HTTPError,ValueError,KeyError):raise HTTPException(401,'No se pudo renovar la autorización; vuelve a conectar Classroom')


def read_pages(client,path,key,params=None,deadline=None):
    result=[];page_token=None
    for _ in range(5):
        if deadline and time.monotonic()>=deadline:raise HTTPException(504,'La sincronización superó el límite total de tiempo; reduce los cursos')
        response=client.get('https://classroom.googleapis.com/v1/'+path,params={'pageSize':100,**(params or {}),**({'pageToken':page_token} if page_token else {})})
        response.raise_for_status();payload=response.json();result.extend(payload.get(key,[]));page_token=payload.get('nextPageToken')
        if not page_token:return result
    raise HTTPException(413,'La sincronización supera el límite de páginas; reduce los cursos autorizados')

@router.get('/history')
def sync_history(user=Depends(current_user),db=Depends(get_db)):
    return [record(x) for x in db.scalars(select(IntegrationSync).where(IntegrationSync.user_id==user.id).order_by(IntegrationSync.created_at.desc()).limit(30))]


@router.post('/sync')
def sync(body:SyncInput,request:Request,user=Depends(current_user),db=Depends(get_db)):
    row=connection(db,user)
    if body.simulation:
        if row and row.mode=='real' and row.status=='connected':raise HTTPException(409,'Desconecta la conexión real antes de usar una simulación')
        if not row:row=IntegrationConnection(user_id=user.id,provider='classroom');db.add(row)
        row.mode='simulated';row.status='simulation';row.last_sync=utcnow()
        db.add(IntegrationSync(user_id=user.id,mode='simulated',status='simulation',counts={'imported':0}));db.commit()
        return {'simulation':True,'courses':[{'name':'Curso ficticio · Classroom demo','id':'demo-course'}],'tasks':[{'title':'Actividad ficticia de demostración','source':'Simulación; no se importa como tarea académica real'}],'imported':0,'message':'Simulación identificada. No se ha contactado con Google ni se han creado tareas reales.'}
    token=access_token(db,user,request.app.state.settings)
    try:
        count=0;changes=0;materials=[];pending_dates=[];submissions=[];deadline=time.monotonic()+60
        with httpx.Client(timeout=8,trust_env=False,headers={'Authorization':'Bearer '+token}) as client:
            courses=read_pages(client,'courses','courses',deadline=deadline)
            if len(courses)>10:raise HTTPException(413,'La sincronización admite hasta diez cursos por revisión; requiere un filtro de cursos para cuentas mayores')
            for course in courses:
                ident=quote(str(course['id']),safe='')
                coursework=read_pages(client,f'courses/{ident}/courseWork','courseWork',deadline=deadline)
                if user.role=='student':
                    for submission in read_pages(client,f'courses/{ident}/courseWork/-/studentSubmissions','studentSubmissions',params={'userId':'me'},deadline=deadline):
                        submissions.append({'course_id':course['id'],'coursework_id':submission.get('courseWorkId'),'state':submission.get('state'),'late':bool(submission.get('late')),'updated_at':submission.get('updateTime')})
                for material in read_pages(client,f'courses/{ident}/courseWorkMaterials','courseWorkMaterial',deadline=deadline):
                    materials.append({'course':course.get('name',''),'title':str(material.get('title',''))[:180],'description':str(material.get('description',''))[:1200],'url':material.get('alternateLink','')})
                for task in coursework:
                    if not task.get('dueDate'):continue
                    if 'dueTime' not in task:
                        pending_dates.append({'title':str(task['title'])[:180],'date':task['dueDate'],'reason':'La fuente no indica hora; requiere revisión antes de asignar una entrega interna'});continue
                    key=f'classroom:{user.id}:{task["id"]}'
                    existing=db.scalar(select(PersonalTask).where(PersonalTask.external_key==key))
                    date=task['dueDate'];clock=task.get('dueTime',{})
                    # Classroom dueTime is UTC, not the browser's local clock.
                    due=datetime(date['year'],date['month'],date['day'],clock.get('hours',0),clock.get('minutes',0),tzinfo=timezone.utc)
                    changed=existing is None or existing.title!=str(task['title'])[:180] or existing.description!=str(task.get('description',''))[:6000] or existing.due_at!=due
                    if not existing:existing=PersonalTask(user_id=user.id,external_key=key,title=str(task['title'])[:180],due_at=due,source='Google Classroom · solo lectura');db.add(existing)
                    existing.title=str(task['title'])[:180];existing.description=str(task.get('description',''))[:6000];existing.due_at=due;count+=1
                    if changed:
                        changes+=1
                        from .education import notify
                        from .notifications import DEFAULT
                        if {**DEFAULT,**user.preferences.get('notification_options',{})}['enabled']:
                            fingerprint=hashlib.sha256((existing.title+existing.description+due.isoformat()).encode()).hexdigest()[:20]
                            notify(db,user.id,'Cambio en Classroom: '+existing.title,'Revisa la tarea importada; no se ha modificado la información oficial de Google.','assignment',key+':'+fingerprint)
        row=connection(db,user);row.last_sync=utcnow();row.last_error=''
        db.add(IntegrationSync(user_id=user.id,mode='real',status='completed',counts={'courses':len(courses),'imported':count,'changed':changes,'materials':len(materials),'submissions':len(submissions)}));db.commit()
        return {'simulation':False,'courses':[{'id':c['id'],'name':c.get('name','')} for c in courses],'imported':count,'changed':changes,'materials_read':len(materials),'materials':materials[:100],'submissions':submissions[:100],'pending_dates':pending_dates[:100],'read_only':True}
    except (httpx.HTTPError,ValueError,KeyError,HTTPException) as exc:
        db.rollback()
        db.add(IntegrationSync(user_id=user.id,mode='real',status='failed',counts={},error_code=str(exc.status_code) if isinstance(exc,HTTPException) else type(exc).__name__));db.commit()
        if isinstance(exc,HTTPException):raise
        raise HTTPException(502,'No se pudo completar la sincronización; no se han guardado resultados parciales')


@router.post('/revoke')
def revoke(request:Request,user=Depends(current_user),db=Depends(get_db)):
    row=connection(db,user);remote=None
    if row and row.mode=='real' and row.encrypted_payload:
        tokens=decode(request.app.state.settings,row.encrypted_payload)
        try:
            with httpx.Client(timeout=10,trust_env=False) as client:response=client.post('https://oauth2.googleapis.com/revoke',data={'token':tokens.get('refresh_token') or tokens.get('access_token')});remote=response.status_code==200
        except httpx.HTTPError:remote=False
    if row:row.encrypted_payload='';row.status='disconnected';row.expires_at=None
    db.execute(delete(OAuthAttempt).where(OAuthAttempt.user_id==user.id));db.commit()
    return {'local_disconnected':True,'remote_revoked':remote,'message':'Conexión local eliminada.'+(' Google no confirmó la revocación; revisa también los permisos en tu cuenta de Google.' if remote is False else '')}
