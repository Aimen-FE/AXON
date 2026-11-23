"""Build a NEW fictional template; never copy a user's database or credentials."""
from dataclasses import replace
from pathlib import Path
import json,secrets,shutil
from sqlalchemy import select
from .config import Settings,ROOT
from .db import create_db,utcnow
from .models import User,Center,InstitutionalSource,Document
from .seed import seed_demo
from .atlas import bootstrap


def prepare(destination=None,public_source=None):
    from .main import migrate
    from .institutional import CURATED,import_source
    destination=(destination or ROOT/'data/teacher-demo').resolve()
    if destination.exists():
        path=destination/'remote-demo.json'
        if not path.is_file() or json.loads(path.read_text()).get('profile')!='teacher-fictitious-v1':raise ValueError('No se reutiliza una carpeta sin marcador de profesor')
        return {'prepared':str(destination),'existing':True}
    if destination.parent!=(ROOT/'data').resolve():raise ValueError('La plantilla solo se crea en una carpeta nueva del proyecto')
    destination.mkdir(mode=0o700,parents=True);(destination/'uploads').mkdir(mode=0o700)
    settings=replace(Settings.from_env(),data_dir=destination,database_url=f'sqlite:///{destination}/axon.sqlite3',demo=True,remote_demo=False,public_demo=False,full_demo=False)
    migrate(settings);engine,factory=create_db(settings.database_url)
    try:
        with factory() as db:
            seed_demo(db,settings);bootstrap(db);db.commit();owner=db.scalar(select(User).where(User.username=='admin.demo'))
            from .nebula import populate
            populate(db, settings, center_id=owner.center_id)
            db.commit()
            for user in db.scalars(select(User)):user.active=False;user.password_hash=''
            db.commit();center=db.scalar(select(Center.id))
            marker={'profile':'teacher-fictitious-v1','center_id':center,'generated_at':utcnow().isoformat(),'personal_data_copied':False}
            path=destination/'remote-demo.json';path.write_text(json.dumps(marker,indent=2));path.chmod(0o600)
        models=ROOT/'data/models'
        if models.is_dir():(destination/'models').symlink_to(models,target_is_directory=True)
        (destination/'axon.sqlite3').chmod(0o600)
        return {'prepared':str(destination),'private_database_copied':False,'fictional_documents':5}
    finally:engine.dispose()

if __name__=='__main__':print(json.dumps(prepare(),ensure_ascii=False))
