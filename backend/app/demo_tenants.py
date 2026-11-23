"""Clone and remove a fictional school namespace without crossing visitors."""
import copy,os,secrets
from pathlib import Path
from sqlalchemy import select,or_,insert,delete
from .db import Base,new_id,utcnow
from .models import User,Center,Document


def rows_for(db,center_id):
    tables=list(Base.metadata.sorted_tables);ids={'centers':{center_id}};rows={}
    # FKs are normally topologically ordered. A second pass also handles nullable
    # self references; each row remains confined to a validated fictitious center.
    for _ in range(3):
        changed=False
        for table in tables:
            if 'id' not in table.c:continue
            if table.name=='centers':condition=table.c.id==center_id
            else:
                clauses=[fk.parent.in_(ids[fk.column.table.name]) for fk in table.foreign_keys if ids.get(fk.column.table.name)]
                if not clauses:continue
                condition=or_(*clauses)
            selected=[dict(row) for row in db.execute(select(table).where(condition)).mappings()]
            if any('center_id' in r and r['center_id']!=center_id for r in selected):raise ValueError('Una referencia cruza el ámbito de la demostración')
            found={r['id'] for r in selected}
            if found:rows[table.name]=selected
            if found!=ids.get(table.name,set()):changed=True;ids[table.name]=found
        if not changed:break
    return tables,rows


def remap(value,mapping):
    if isinstance(value,str):return mapping.get(value,value)
    if isinstance(value,list):return [remap(v,mapping) for v in value]
    if isinstance(value,dict):return {k:remap(v,mapping) for k,v in value.items()}
    return copy.deepcopy(value)


def clone(db,settings,template_id,perspective="teacher"):
    tables,rows=rows_for(db,template_id);mapping={r['id']:new_id() for values in rows.values() for r in values}
    teacher=next(r for r in rows['users'] if r['username']=={'teacher':'profesor.demo','student':'alumno.demo','admin':'admin.demo'}[perspective])
    visitor_id=mapping[teacher['id']];center_id=mapping[template_id];nonce=secrets.token_hex(10);copied=[]
    try:
        for table in tables:
            values=[]
            for old in rows.get(table.name,[]):
                row=remap(old,mapping);row['created_at']=utcnow();row['updated_at']=utcnow()
                if table.name=='users':
                    row.update(username='demo.'+nonce+'.'+str(len(values)),password_hash='',is_demo=True,active=old['role'] in ('student','teacher'))
                    row['preferences']={**row['preferences'],'demo_roster':True,'demo_identity':old['username']}
                    if row['id']==visitor_id:row.update(active=True,role=perspective,display_name=old['display_name'],preferences={**row['preferences'],'demo_teacher':True,'automatic_personal_actions':False})
                if table.name=='learning_classes':row['join_hash']=None
                if table.name=='documents':
                    source=settings.data_dir/'uploads'/old['storage_key']
                    if source.is_symlink() or not source.resolve().is_relative_to((settings.data_dir/'uploads').resolve()):raise ValueError('Archivo fuera de la plantilla')
                    suffix=Path(old['storage_key']).suffix;key=row['id']+suffix;target=settings.data_dir/'uploads'/key
                    fd=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
                    with os.fdopen(fd,'wb') as out,source.open('rb') as stream:
                        import shutil
                        shutil.copyfileobj(stream,out)
                    copied.append(target);row['storage_key']=key
                if table.name=='notifications' and row.get('dedup_key'):row['dedup_key']=nonce+':'+row['dedup_key']
                if table.name=='provider_policies':row['payload']={**row['payload'],'cloud':{'provider':'gemini','enabled':False,'model':''}}
                values.append(row)
            if values:db.execute(insert(table),values)
        db.flush()
        return db.get(User,visitor_id),center_id,copied
    except Exception:
        for path in copied:path.unlink(missing_ok=True)
        raise


def remove(db,settings,center_id,template_id):
    if center_id==template_id:raise ValueError('No se elimina la plantilla de demostración')
    users=list(db.scalars(select(User).where(User.center_id==center_id)))
    if not users or any(not u.is_demo or u.password_hash for u in users):raise ValueError('La eliminación requiere un centro exclusivamente ficticio')
    tables,rows=rows_for(db,center_id)
    paths=[]
    for row in rows.get('documents',[]):
        path=settings.data_dir/'uploads'/row['storage_key']
        if path.is_symlink() or not path.resolve().is_relative_to((settings.data_dir/'uploads').resolve()):raise ValueError('Archivo fuera de la carpeta de demostración')
        paths.append(path)
    for table in reversed(tables):
        values=rows.get(table.name,[])
        if values:db.execute(delete(table).where(table.c.id.in_([row['id'] for row in values])))
    db.commit()
    for path in paths:path.unlink(missing_ok=True)
    db.expire_all()
