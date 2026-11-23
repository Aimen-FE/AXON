"""Operator-only, backed-up retirement of institutional data using a private manifest."""
import argparse
from contextlib import closing
from dataclasses import replace
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sqlite3
import unicodedata

from sqlalchemy.engine import make_url

from .backup import backup, restore
from .config import Settings
from .nebula import CENTER_NAME, CODE, COUNTRY, TOWN


def normalized(value):
    return ''.join(c for c in unicodedata.normalize('NFKD', str(value).lower()) if not unicodedata.combining(c))


def identifier(name):
    return '"' + name.replace('"', '""') + '"'


def retire(settings, manifest, destination):
    """Migrate a stopped SQLite installation while preserving accounts and unrelated data."""
    if not settings.database_url.startswith('sqlite:'):
        raise ValueError('La retirada controlada admite SQLite')
    source = Path(make_url(settings.database_url).database).resolve()
    destination = Path(destination).resolve()
    if destination.exists() or destination.is_relative_to(settings.data_dir.resolve()):
        raise ValueError('La copia debe ir a una carpeta nueva fuera de los datos activos')
    terms = [normalized(item) for item in manifest['terms'] if len(item.strip()) >= 4]
    if not terms:
        raise ValueError('Indica las referencias que deban retirarse en un manifiesto privado')
    affected = lambda value: any(term in normalized(value) for term in terms)
    destination.mkdir(mode=0o700, parents=True)
    archive = backup(settings, destination / 'private-backup.zip')
    restored = restore(archive, destination / 'restore-check')
    with closing(sqlite3.connect(source.as_uri()+'?mode=ro',uri=True)) as original, closing(sqlite3.connect(restored/'axon.sqlite3')) as checked:
        for statement in ('PRAGMA integrity_check','PRAGMA foreign_key_check'):
            if checked.execute(statement).fetchall() != original.execute(statement).fetchall():
                raise ValueError('La copia no coincide con la integridad de la base original')
        accounts = original.execute('SELECT id,username,role,active,password_hash FROM users ORDER BY id').fetchall()
        if accounts != checked.execute('SELECT id,username,role,active,password_hash FROM users ORDER BY id').fetchall():
            raise ValueError('La copia no conserva las cuentas')
    removed_keys = []
    result = {'backup':str(archive),'centers':0,'documents':0,'fields':0}
    with closing(sqlite3.connect(source)) as db:
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        db.execute('PRAGMA secure_delete=ON')
        db.execute('BEGIN IMMEDIATE')
        tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        centers = {row['id'] for row in db.execute('SELECT * FROM centers')
                   if affected(' '.join(str(value) for value in row))}
        if 'core_states' in tables:
            centers.update(row['center_id'] for row in db.execute('SELECT * FROM core_states') if affected(row['payload']))
        owners = {row['id'] for row in db.execute('SELECT id,center_id FROM users') if row['center_id'] in centers}
        for doc in list(db.execute('SELECT * FROM documents')):
            if doc['center_id'] in centers or affected(' '.join(str(value) for value in doc)):
                removed_keys.append(doc['storage_key'])
                db.execute('DELETE FROM documents WHERE id=?',(doc['id'],))
        for center_id in sorted(centers):
            row = db.execute('SELECT * FROM centers WHERE id=?',(center_id,)).fetchone()
            config = json.loads(row['settings'] or '{}')
            config = {k:v for k,v in config.items() if k not in ('public_info','school_calendar','schedule_code_map')}
            config.update(fictional=True,country=COUNTRY,code=CODE)
            db.execute('UPDATE centers SET name=?,town=?,settings=? WHERE id=?',
                       (CENTER_NAME,TOWN,json.dumps(config,ensure_ascii=False),center_id))
            payload={'name':'AXON','center_name':CENTER_NAME,'town':TOWN,'region':'','country':COUNTRY,
                     'center_code':CODE,'website':'','mission':'Ayudar a aprender y organizar un entorno educativo ficticio.',
                     'audience':'Alumnado, profesorado y administración de demostración.'}
            for table in ('core_states','core_revisions'):
                if table in tables:
                    db.execute(f'UPDATE {table} SET payload=? WHERE center_id=?',(json.dumps(payload,ensure_ascii=False),center_id))
        for table, label in (('groups','Grupo ficticio'),('classrooms','Aula ficticia')):
            if table in tables:
                for number,row in enumerate(db.execute('SELECT id,center_id FROM '+table+' ORDER BY id'),1):
                    if row['center_id'] in centers:
                        db.execute('UPDATE '+table+' SET name=? WHERE id=?',(f'{label} {number:03d}',row['id']))
        # Imported private curricula and contacts are retired with their sources.
        for table,column in (('knowledge_sources','owner_id'),('academic_teachers','owner_id'),
                             ('semantic_vectors','user_id'),('integration_syncs','user_id')):
            if table in tables and owners:
                db.execute(f'DELETE FROM {table} WHERE {column} IN ({",".join("?" for _ in owners)})',tuple(owners))
        # Purge exact institutional strings from narratives, metadata and historical proposals.
        def sanitize(value):
            if isinstance(value,str):
                return 'Referencia institucional retirada · entorno ficticio' if affected(value) else value
            if isinstance(value,list):
                return [sanitize(item) for item in value]
            if isinstance(value,dict):
                return {sanitize(key):sanitize(item) for key,item in value.items()}
            return value
        excluded={'password_hash','token_hash','csrf_token','encrypted_payload','encrypted_verifier','storage_key','checksum'}
        for table in sorted(tables):
            if table.startswith(('sqlite_','search_')):
                continue
            columns=list(db.execute('PRAGMA table_info('+identifier(table)+')'))
            if not any(col[1]=='id' for col in columns):
                continue
            for column in columns:
                name,kind=column[1],column[2].upper()
                if name in excluded or not any(x in kind for x in ('TEXT','CHAR','JSON')):
                    continue
                for row in list(db.execute('SELECT id,'+identifier(name)+' FROM '+identifier(table)+' WHERE '+identifier(name)+' IS NOT NULL')):
                    value=row[name]
                    if not affected(value):
                        continue
                    try:
                        parsed=json.loads(value) if kind=='JSON' else value
                    except (ValueError,TypeError):
                        parsed=value
                    output=sanitize(parsed)
                    output=json.dumps(output,ensure_ascii=False) if kind=='JSON' else output
                    # Do not mutate account identifiers or permissions.
                    if table=='users' and name in ('username','role'):
                        continue
                    db.execute('UPDATE '+identifier(table)+' SET '+identifier(name)+'=? WHERE id=?',(output,row['id']))
                    result['fields']+=1
        if db.execute('PRAGMA foreign_key_check').fetchall():
            db.rollback()
            raise ValueError('La retirada afectaría a una relación no prevista')
        assert accounts == [tuple(row) for row in db.execute('SELECT id,username,role,active,password_hash FROM users ORDER BY id')]
        db.commit()
        db.execute('PRAGMA wal_checkpoint(TRUNCATE)')
        db.execute('VACUUM')
        assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
    # Files remain in the verified private backup. Only retired active originals are removed.
    for key in removed_keys:
        path=settings.data_dir/'uploads'/key
        if path.parent.resolve()==(settings.data_dir/'uploads').resolve() and path.is_file() and not path.is_symlink():
            path.unlink()
    result.update(centers=len(centers),documents=len(removed_keys))
    (destination/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    return result


def main():
    parser=argparse.ArgumentParser(description='Retirar referencias institucionales con copia privada restaurada y verificada')
    parser.add_argument('--database',required=True,type=Path)
    parser.add_argument('--manifest',required=True,type=Path)
    parser.add_argument('--backup',required=True,type=Path)
    args=parser.parse_args()
    os.umask(0o077)
    settings=replace(Settings.from_env(),data_dir=args.database.resolve().parent,
                     database_url='sqlite:///'+str(args.database.resolve()))
    print(json.dumps(retire(settings,json.loads(args.manifest.read_text()),args.backup),ensure_ascii=False))


if __name__=='__main__':
    main()
