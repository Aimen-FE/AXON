from conftest import DEMO_TEST_PASSWORD
from dataclasses import replace
from pathlib import Path
import io,json,zipfile
import pytest
from sqlalchemy import select,text
from app.backup import backup,restore
from app.main import create_app
from app.models import User,Message
from test_documents import upload
from test_memory_chat import send


def test_backup_restore_preserves_database_files_and_search(app,login,tmp_path):
    c=login();convo=c.post('/api/conversations',json={}).json()['id'];send(c,convo,'Recuerda restauración de prueba')
    doc=upload(c,'backup.txt',b'Contenidos de copia verificable').json()
    file=backup(app.state.settings,tmp_path/'snapshot.zip')
    destination=restore(file,tmp_path/'restored')
    new_settings=replace(app.state.settings,data_dir=destination,database_url=f'sqlite:///{destination}/axon.sqlite3')
    other=create_app(new_settings,maintenance=False)
    from fastapi.testclient import TestClient
    with TestClient(other) as client:
        r=client.post('/api/auth/login',json={'username':'alumno.demo','password':DEMO_TEST_PASSWORD});assert r.status_code==200
        assert len(client.get('/api/conversations/'+convo).json()['messages'])==2
        assert client.get('/api/documents/'+doc['id']+'/download').content==b'Contenidos de copia verificable'
        assert client.get('/api/memory?q=restauracion').json()['memories']
    with pytest.raises(ValueError):restore(file,destination)
    with pytest.raises(ValueError):backup(app.state.settings,file)


def test_restore_refuses_path_traversal_before_creating_destination(tmp_path):
    file=tmp_path/'bad.zip'
    with zipfile.ZipFile(file,'w') as z:
        z.writestr('manifest.json',json.dumps({'format':'axon-backup-v1'}))
        z.writestr('axon.sqlite3',b'not important')
        z.writestr('../escape.txt','forbidden')
    destination=tmp_path/'new'
    with pytest.raises(ValueError):restore(file,destination)
    assert not destination.exists()
    assert not (tmp_path/'escape.txt').exists()


def test_foreign_keys_and_fts_integrity(app):
    with app.state.engine.connect() as connection:
        assert connection.exec_driver_sql('PRAGMA foreign_key_check').fetchall()==[]
        assert connection.exec_driver_sql('PRAGMA integrity_check').scalar()=='ok'
        assert connection.exec_driver_sql('SELECT version_num FROM alembic_version').scalar()=='0008'
