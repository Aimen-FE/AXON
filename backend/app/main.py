import asyncio
import logging
import time
from datetime import datetime,timezone
from collections import deque
from contextlib import asynccontextmanager,suppress
from pathlib import Path
from fastapi import FastAPI,Request,Depends
from fastapi.responses import JSONResponse,FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware
from sqlalchemy import select,text
from sqlalchemy.exc import IntegrityError,SQLAlchemyError
from alembic import command
from alembic.config import Config
from .config import Settings,ROOT
from .db import create_db
from .ai import OllamaAdapter
from . import auth,memory,education,tools,documents,reports,chat,admin,knowledge,study,research,classroom,notifications,orchestrator,mathematics,semantic,extensions,scheduler,materials,operations,universal,atlas,institutional,media,providers,remote,guest,demo_launch,teacher_demo,teacher_launch,classes,class_files,class_calendar,classwork,class_assistant,education_settings
from .models import Center,Document,CalendarEvent
from .seed import seed_demo

logger=logging.getLogger('axon')
logging.basicConfig(level=logging.INFO,format='%(asctime)s %(levelname)s %(name)s %(message)s')


def migrate(settings):
    import os
    # Alembic env obtains the same URL; preserve the caller's process configuration.
    config=Config(str(ROOT/'backend'/'alembic.ini'))
    config.attributes['database_url']=settings.database_url
    command.upgrade(config,'head')


def create_app(settings=None,initialize=True,maintenance=True,demo_passwords=None):
    settings=settings or Settings.from_env()
    if settings.public_demo and (settings.data_dir.resolve()==(ROOT/'data').resolve() or not (settings.data_dir/'remote-demo.json').is_file()):raise ValueError('La demo pública requiere una base ficticia preparada')
    if settings.remote_demo:
        if settings.data_dir.resolve()==(ROOT/'data').resolve() or not (settings.data_dir/'remote-demo.json').is_file():raise ValueError('Prepara primero una base ficticia separada; no se inicia el acceso remoto con la instalación personal')
    settings.data_dir.mkdir(parents=True,exist_ok=True,mode=0o700)
    (settings.data_dir/'uploads').mkdir(exist_ok=True,mode=0o700)
    settings.data_dir.chmod(0o700)
    (settings.data_dir/'uploads').chmod(0o700)
    engine,factory=create_db(settings.database_url)
    if initialize:
        migrate(settings)
        for private_file in settings.data_dir.glob('*.sqlite3*'):
            if private_file.is_file(): private_file.chmod(0o600)
        with factory() as db:
            if demo_passwords is not None:
                seed_demo(db,settings,demo_passwords)
            atlas.bootstrap(db);db.commit()
    if settings.remote_demo:
        with factory() as db:remote.validate_profile(settings,db)
    if settings.full_demo:
        with factory() as db:teacher_demo.validate_profile(settings,db)
    elif settings.public_demo:
        with factory() as db:guest.validate_profile(settings,db)

    async def maintenance_loop():
        while True:
            try:
                def job():
                    if settings.full_demo:
                        with factory() as db:teacher_demo.cleanup(db,settings)
                        scheduler.tick(factory,settings)
                    elif settings.public_demo:
                        with factory() as db:guest.cleanup(db)
                    else:
                        with factory() as db:reports.daily_maintenance(db)
                        scheduler.tick(factory,settings)
                await asyncio.to_thread(job)
            except Exception:logger.exception('Fallo en revisión programada; se reintentará')
            await asyncio.sleep(60 if settings.public_demo else 300)

    @asynccontextmanager
    async def lifespan(app):
        task=asyncio.create_task(maintenance_loop()) if maintenance else None
        yield
        if task:
            task.cancel()
            with suppress(asyncio.CancelledError):await task
        if settings.full_demo:
            with factory() as db:teacher_demo.cleanup(db,settings,all_sessions=True)
        elif settings.public_demo:
            from sqlalchemy import update
            from .models import GuestSession
            with factory() as db:
                db.execute(update(GuestSession).values(revoked=True));db.commit();guest.cleanup(db)
        engine.dispose()

    app=FastAPI(title='AXON',version='0.7.0',description='Plataforma educativa con autorización independiente de IA y confirmación de cambios académicos.',
                docs_url=None if settings.public_demo else '/api/docs',openapi_url=None if settings.public_demo else '/api/openapi.json',redoc_url=None,lifespan=lifespan)
    app.state.settings=settings
    app.state.engine=engine
    app.state.session_factory=factory
    app.state.ai=OllamaAdapter(settings)
    app.state.chat_inflight=0
    app.state.active_generations={}
    app.state.access_verifier=remote.AccessVerifier(settings)
    app.state.remote_limits={}
    app.state.metrics=deque(maxlen=300)
    app.add_middleware(TrustedHostMiddleware,allowed_hosts=['localhost','127.0.0.1','testserver','[::1]',*settings.allowed_hosts]+([settings.public_hostname] if settings.remote_demo else [])+([settings.public_origin_host] if settings.public_demo else []))

    @app.middleware('http')
    async def security_headers(request:Request,call_next):
        blocked=await (teacher_demo.guard(request,app) if settings.full_demo else guest.guard(request,app))
        if blocked is not None:return blocked
        blocked=await remote.guard(request,app)
        if blocked is not None:return blocked
        if request.method not in ('GET','HEAD','OPTIONS'):
            origin=request.headers.get('origin')
            if (origin and origin not in ((getattr(request.state,'public_origin',''),) if settings.public_demo else settings.allowed_origins)) or request.headers.get('sec-fetch-site')=='cross-site':
                return JSONResponse({'detail':'Origen de petición no autorizado'},403)
        length=request.headers.get('content-length')
        max_body=16*1024 if (settings.public_demo and not settings.full_demo) or request.url.path=='/api/teacher-demo/start' else settings.max_upload+1024*1024
        if length and (not length.isdigit() or int(length)>max_body):
            return JSONResponse({'detail':'Petición demasiado grande'},413)
        if request.method in ('POST','PUT','PATCH'):
            data=[];received=0
            async for part in request.stream():
                received+=len(part)
                if received>max_body:return JSONResponse({'detail':'Petición demasiado grande'},413)
                data.append(part)
            request._body=b''.join(data)
        started=time.monotonic()
        response=await call_next(request)
        route=request.scope.get('route')
        if request.url.path.startswith('/api'):
            app.state.metrics.append({'route':getattr(route,'path','unmatched'),'status':response.status_code,'duration_ms':round((time.monotonic()-started)*1000),'checked_at':datetime.now(timezone.utc).isoformat()})
        if settings.remote_demo or settings.public_demo:response.headers['Strict-Transport-Security']='max-age=31536000'
        response.headers['X-Content-Type-Options']='nosniff'
        response.headers['X-Frame-Options']='DENY'
        response.headers['Referrer-Policy']='no-referrer'
        response.headers['Permissions-Policy']='camera=(), microphone=(self), geolocation=()'
        if request.url.path.startswith('/api'):
            response.headers['Cache-Control']='no-store'
        elif request.url.path=='/sw.js':
            response.headers['Cache-Control']='no-cache'
        if not request.url.path.startswith('/api/docs'):
            response.headers['Content-Security-Policy']="default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; media-src 'self' blob:; connect-src 'self'; font-src 'self'; frame-ancestors 'none'; object-src 'none'; base-uri 'self'; form-action 'self'"
        return response

    from fastapi.exceptions import RequestValidationError
    @app.exception_handler(RequestValidationError)
    async def validation_error(request,exc):
        return JSONResponse({'detail':[{'loc':list(e['loc']),'msg':e['msg'],'type':e['type']} for e in exc.errors()]},422)

    @app.exception_handler(IntegrityError)
    async def integrity_error(request,exc):
        return JSONResponse({'detail':'La operación entra en conflicto con otro registro. Actualiza los datos e inténtalo de nuevo'},409)

    @app.exception_handler(SQLAlchemyError)
    async def db_error(request,exc):
        logger.error('Error de base de datos en %s',request.url.path)
        return JSONResponse({'detail':'No se ha podido guardar la operación. Inténtalo de nuevo'},503)

    for router in (auth.router,memory.router,education.router,tools.router,documents.router,reports.router,chat.router,admin.router,knowledge.router,study.router,research.router,classroom.router,notifications.router,orchestrator.router,mathematics.router,semantic.router,extensions.router,scheduler.router,materials.router,operations.router,universal.router,atlas.router,institutional.router,media.router,providers.router,remote.router,guest.router,teacher_launch.router,teacher_demo.router,classes.router,class_files.router,class_calendar.router,classwork.router,class_assistant.router,education_settings.router):
        app.include_router(router,prefix='/api')

    @app.get('/api/health')
    def health():
        with engine.connect() as conn:conn.execute(text('SELECT 1'))
        return {'status':'ok','version':'0.7.0','demo':settings.demo,'timezone':'Europe/Madrid'}

    @app.get('/api/public/connection')
    def public_connection(request: Request):
        if not settings.pages_origin:
            return JSONResponse({'detail':'Comprobación externa desactivada'}, status_code=404)
        origin = request.headers.get('origin')
        if origin and origin != settings.pages_origin:
            return JSONResponse({'detail':'Origen de comprobación no autorizado'}, status_code=403)
        headers = {'Vary': 'Origin'}
        if origin == settings.pages_origin:
            headers['Access-Control-Allow-Origin'] = origin
        with engine.connect() as conn:
            conn.execute(text('SELECT 1'))
        return JSONResponse({'service':'axon','status':'ok','version':app.version,'auth':'same-origin'}, headers=headers)

    @app.get('/api/system')
    async def system(user=Depends(auth.current_user),db=Depends(auth.get_db)):
        from .documents import ocr_available
        import os
        ai_status=await app.state.ai.status();chosen=providers.local_policy(db,user,settings)['model']
        ai_status={**ai_status,'model':chosen,'available':chosen in ai_status.get('models',[])}
        if settings.public_demo:ai_status={k:v for k,v in ai_status.items() if k!='models'}
        return {'ai':ai_status,'internet':not settings.public_demo and bool(os.getenv('AXON_SEARCH_URL')),'public_url_reader':not settings.public_demo or settings.full_demo,'ocr':ocr_available(),'demo':user.is_demo,'voice':media.status() if not settings.public_demo or settings.full_demo else {'speech':False,'transcription':False},'remote_demo':settings.remote_demo,'public_demo':settings.public_demo,'full_demo':settings.full_demo}

    @app.get('/api/public/info')
    def public_info():
        with factory() as db:
            if settings.full_demo:
                center = db.get(Center, teacher_demo.marker(settings)['center_id'])
            else:
                centers = list(db.scalars(select(Center).order_by(Center.created_at)))
                center = next((item for item in centers if not item.settings.get('private_workspace')), None)
            if not center:
                has_center = db.scalar(select(Center.id).limit(1))
                return {'center': None, 'documents': [], 'setup_required': not has_center}
            docs=list(db.scalars(select(Document).where(Document.center_id==center.id,Document.access=='public',Document.status.in_(['validated','official']))))
            return {'center':{'name':center.name,'town':center.town},'remote_demo':settings.remote_demo,'public_demo':settings.public_demo,'guest_duration_minutes':1440 if settings.full_demo else 60,'guest_queries':teacher_demo.QUERIES_PER_HOUR if settings.full_demo else guest.MAX_REQUESTS,'demo':settings.demo,**({'full_demo':True,'teacher_session_hours':24} if settings.full_demo else {}),'documents':[{'id':d.id,'title':d.title,'source':d.source} for d in docs]}

    dist=ROOT/'frontend'/'dist'
    if (dist/"assets").is_dir():
        app.mount('/assets',StaticFiles(directory=dist/'assets'),name='assets')
        @app.get('/{path:path}',include_in_schema=False)
        def frontend(path:str):
            if path=='api' or path.startswith('api/'):
                return JSONResponse({'detail':'Ruta no disponible'},404)
            target=(dist/path).resolve()
            if target.is_relative_to(dist.resolve()) and target.is_file():return FileResponse(target)
            if Path(path).suffix:return JSONResponse({'detail':'Archivo no disponible'},404)
            return FileResponse(dist/'index.html',headers={'Cache-Control':'no-cache'})
    return app


def app_factory():
    return create_app()
