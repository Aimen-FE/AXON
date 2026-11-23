import secrets
from contextlib import ExitStack
from dataclasses import replace
import pytest
from fastapi.testclient import TestClient
from app.main import create_app
from app.config import Settings
from app.seed import DEMO_ACCOUNTS

DEMO_TEST_PASSWORD = secrets.token_urlsafe(24)
DEMO_PASSWORDS = {user[0]: DEMO_TEST_PASSWORD for user in DEMO_ACCOUNTS}


@pytest.fixture
def app(tmp_path):
    settings=replace(Settings.from_env(),data_dir=tmp_path,database_url=f'sqlite:///{tmp_path}/test.sqlite3',demo=True,ai_mode='simulated')
    application=create_app(settings,maintenance=False,demo_passwords=DEMO_PASSWORDS)
    yield application
    application.state.engine.dispose()


@pytest.fixture
def login(app):
    with ExitStack() as stack:
        def connect(username='alumno.demo'):
            client=stack.enter_context(TestClient(app))
            response=client.post('/api/auth/login',json={'username':username,'password':DEMO_TEST_PASSWORD})
            assert response.status_code==200,response.text
            client.headers['x-csrf-token']=response.json()['csrf_token']
            client.user=response.json()['user']
            return client
        yield connect


def exam_args(client,**changes):
    meta=client.get('/api/academic').json()
    data={'title':'Examen de regresión','kind':'exam','visibility':'group',
          'group_id':next(g['id'] for g in meta['groups'] if 'Bachillerato' in g['name']),'subject_id':next(s['id'] for s in meta['subjects'] if s['name']=='Matemáticas'),
          'starts_at':'2030-12-19T09:00:00+01:00','ends_at':'2030-12-19T10:00:00+01:00','syllabus':'Funciones'}
    data.update(changes)
    return data
