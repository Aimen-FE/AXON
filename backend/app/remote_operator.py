"""Operator-only preparation. Never creates a tunnel, DNS record or cloud resource."""
import argparse,json,os,secrets
from pathlib import Path
from dataclasses import replace
from sqlalchemy import select,delete
from .config import Settings,ROOT
from .models import User,Center,Teaching,Session
from .db import create_db,utcnow
from .main import migrate
from .seed import seed_demo
from .atlas import bootstrap
from .remote import issue

ALLOWED={'AXON_DATA_DIR','AXON_DATABASE_URL','AXON_REMOTE_DEMO','AXON_PUBLIC_HOSTNAME','AXON_ACCESS_ISSUER','AXON_ACCESS_AUDIENCE','AXON_COOKIE_SECURE','AXON_ALLOWED_ORIGINS','AXON_DEMO','AXON_AI_MODE','AXON_OLLAMA_MODEL','AXON_MEDIA_MODELS_DIR'}

def prepare(destination):
    destination=destination.resolve()
    if not destination.is_relative_to(ROOT/'data') or destination==ROOT/'data' or destination.exists():raise ValueError('Usa una subcarpeta NUEVA dentro de data; nunca la instalación personal')
    s=replace(Settings.from_env(),data_dir=destination,database_url=f'sqlite:///{destination}/axon.sqlite3',demo=True,remote_demo=False)
    destination.mkdir(parents=True,mode=0o700);(destination/'uploads').mkdir(mode=0o700)
    migrate(s);engine,factory=create_db(s.database_url)
    with factory() as db:
        seed_demo(db,s);center=db.scalar(select(Center))
        from .nebula import populate
        populate(db,s,center.id)
        bootstrap(db)
        template=list(db.scalars(select(Teaching).join(User,Teaching.teacher_id==User.id).where(User.username=='profesor.demo')))
        for u in db.scalars(select(User)):u.active=False;u.password_hash=''
        for name,display,role in [('atlas.owner','Operador ficticio ATLAS','admin'),('docente1.invitado','Docente invitado 1','teacher'),('docente2.invitado','Docente invitado 2','teacher'),('docente3.invitado','Docente invitado 3','teacher')]:
            user=User(center_id=center.id,username=name,display_name=display,role=role,active=False,password_hash='',is_demo=True,preferences={});db.add(user);db.flush()
            if role=='teacher':
                for t in template:db.add(Teaching(teacher_id=user.id,group_id=t.group_id,subject_id=t.subject_id))
        db.execute(delete(Session));db.commit()
        marker={'profile':'atlas-fictitious-v1','center_id':center.id,'generated_at':utcnow().isoformat(),'personal_data_copied':False,'cloud_resources_created':False}
        (destination/'remote-demo.json').write_text(json.dumps(marker,indent=2));(destination/'remote-demo.json').chmod(0o600)
    engine.dispose();(destination/'axon.sqlite3').chmod(0o600)
    return {'prepared':str(destination),'accounts':'Operador ficticio y tres docentes independientes, inactivos y sin contraseña hasta su invitación individual.','published':False}

def invite(destination,username,email,hours):
    if not (destination/'remote-demo.json').is_file():raise ValueError('Carpeta ficticia no preparada')
    from .remote import InviteInput
    engine,factory=create_db(f'sqlite:///{destination.resolve()}/axon.sqlite3')
    try:
        with factory() as db:
            target=db.scalar(select(User).where(User.username==username,User.is_demo.is_(True)))
            if not target:raise ValueError('Cuenta ficticia no disponible')
            args=InviteInput(user_id=target.id,email=email,hours=hours);token=issue(db,target,args.email,args.hours);db.commit()
            out=destination/'private-invitations';out.mkdir(exist_ok=True,mode=0o700)
            path=out/(username+'-'+secrets.token_hex(4)+'.json');fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
            with os.fdopen(fd,'w') as stream:json.dump({'username':username,'email':email,'token':token,'expires_hours':hours,'url_fragment':'#invite='+token},stream)
            return {'private_invitation_file':str(path),'sent':False}
    finally:engine.dispose()

def load_config(path):
    # Configuration is data; never source a shell file.
    for line in path.read_text().splitlines():
        line=line.strip()
        if not line or line.startswith('#'):continue
        key,sep,value=line.partition('=')
        if not sep or key not in ALLOWED or not value or value.startswith('RELLENAR'):raise ValueError('Completa los campos permitidos de la configuración remota')
        os.environ[key]=value.strip().strip('\"\'')
    if os.environ.get('AXON_REMOTE_DEMO')!='true':raise ValueError('Este inicio exige el perfil remoto aislado')

def main():
    parser=argparse.ArgumentParser(description='Preparación local de ATLAS; no publica servidores ni envía invitaciones')
    sub=parser.add_subparsers(dest='command',required=True)
    p=sub.add_parser('prepare');p.add_argument('--destination',type=Path,required=True)
    p=sub.add_parser('invite');p.add_argument('--destination',type=Path,required=True);p.add_argument('--username',required=True);p.add_argument('--email',required=True);p.add_argument('--hours',type=int,default=24)
    p=sub.add_parser('check');p.add_argument('--config',type=Path,required=True)
    p=sub.add_parser('serve');p.add_argument('--config',type=Path,required=True)
    args=parser.parse_args()
    if args.command=='prepare':result=prepare(args.destination)
    elif args.command=='invite':result=invite(args.destination,args.username,args.email,args.hours)
    else:
        load_config(args.config);settings=Settings.from_env()
        from .main import create_app
        app=create_app(settings,maintenance=False)
        if args.command=='serve':
            import uvicorn
            uvicorn.run(app,host='127.0.0.1',port=8015,proxy_headers=False,limit_concurrency=24,timeout_keep_alive=5);return
        result={'profile_valid':True,'published':False,'missing':'Verificación del túnel y acceso desde otro dispositivo tras autorización explícita.'}
        app.state.engine.dispose()
    print(json.dumps(result,ensure_ascii=False))
if __name__=='__main__':main()
