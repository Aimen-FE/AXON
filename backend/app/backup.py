"""Copias SQLite+archivos. Detén AXON para tener una instantánea coherente de ambos."""
import json
import os
import sqlite3
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory
from sqlalchemy.engine import make_url


def backup(settings,output):
    if not settings.database_url.startswith('sqlite'):
        raise ValueError('Usa pg_dump y una copia de uploads para PostgreSQL')
    source=Path(make_url(settings.database_url).database).resolve()
    output=Path(output).resolve()
    if not source.is_file():raise ValueError('La base de datos no existe')
    if output.exists():raise ValueError('La copia de destino ya existe; usa otro nombre')
    if output.is_relative_to(settings.data_dir/'uploads'):raise ValueError('La copia debe guardarse fuera de uploads')
    output.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    with TemporaryDirectory() as temp:
        snapshot=Path(temp)/'axon.sqlite3'
        with sqlite3.connect(source) as origin,sqlite3.connect(snapshot) as target:origin.backup(target)
        fd=os.open(output,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
        with os.fdopen(fd,'wb') as stream,zipfile.ZipFile(stream,'w',zipfile.ZIP_DEFLATED) as archive:
            archive.write(snapshot,'axon.sqlite3')
            key=settings.data_dir/'secrets'/'integrations.key'
            if key.is_file() and not key.is_symlink():archive.write(key,'secrets/integrations.key')
            archive.writestr('manifest.json',json.dumps({'format':'axon-backup-v1','database':'axon.sqlite3'}))
            for file in (settings.data_dir/'uploads').glob('*'):
                if file.is_file() and not file.is_symlink():archive.write(file,'uploads/'+file.name)
    output.chmod(0o600)
    return output


def restore(archive_path,destination):
    """Restaura exclusivamente en una carpeta nueva, nunca sobre datos existentes."""
    destination=Path(destination).resolve()
    if destination.exists():raise ValueError('La carpeta de destino debe ser nueva para evitar sobrescrituras')
    with zipfile.ZipFile(archive_path) as archive:
        infos=archive.infolist()
        if len(infos)>10000 or sum(i.file_size for i in infos)>1024*1024*1024:raise ValueError('Copia demasiado grande')
        names={i.filename for i in infos}
        if 'manifest.json' not in names or 'axon.sqlite3' not in names:raise ValueError('Copia no válida')
        if archive.getinfo('manifest.json').file_size>4096:raise ValueError('Manifiesto demasiado grande')
        manifest=json.loads(archive.read('manifest.json'))
        if manifest.get('format')!='axon-backup-v1':raise ValueError('Formato de copia desconocido')
        for entry in infos:
            path=Path(entry.filename)
            if path.is_absolute() or '..' in path.parts or '\\' in entry.filename or entry.is_dir() or entry.flag_bits & 1 or ((entry.external_attr>>16)&0o170000)==0o120000:
                raise ValueError('Ruta insegura en la copia')
            if entry.filename not in ('manifest.json','axon.sqlite3','secrets/integrations.key') and not (len(path.parts)==2 and path.parts[0]=='uploads'):
                raise ValueError('Contenido inesperado en la copia')
        destination.mkdir(parents=True,mode=0o700)
        for entry in infos:
            target=destination/entry.filename
            target.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
            with archive.open(entry) as source,target.open('xb') as out:
                while chunk:=source.read(1024*1024):out.write(chunk)
            target.chmod(0o600)
    with sqlite3.connect(destination/'axon.sqlite3') as db:
        if db.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('La base restaurada no supera la comprobación de integridad')
        if db.execute('PRAGMA foreign_key_check').fetchall():raise ValueError('La copia contiene relaciones inválidas')
    return destination
