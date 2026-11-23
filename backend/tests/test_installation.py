from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import secrets

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.auth import verify
from app.config import Settings
from app.installation import create_first_admin, create_local_demo, demo_profile, reset_password
from app.main import create_app
from app.models import Center, CoreState, Session, User


@pytest.fixture
def clean(tmp_path):
    return replace(Settings.from_env(), demo=False, data_dir=tmp_path,
                   database_url=f'sqlite:///{tmp_path}/axon.sqlite3', ai_mode='simulated')


def provision(settings, password):
    create_first_admin(settings, 'Centro ficticio de prueba', '', 'operador.pruebas', 'Operador de prueba', password)


def authenticate(client, name, password):
    response = client.post('/api/auth/login', json={'username': name, 'password': password})
    assert response.status_code == 200, response.text
    client.headers['x-csrf-token'] = response.json()['csrf_token']
    return response.json()['user']


def test_fresh_instance_has_no_default_accounts_and_operator_bootstrap_is_once(clean):
    app = create_app(clean, maintenance=False)
    with TestClient(app) as client, app.state.session_factory() as db:
        assert not db.scalar(select(Center.id))
        assert not db.scalar(select(User.id))
        assert client.get('/api/public/info').json()['setup_required']
        assert client.post('/api/auth/login', json={'username': 'admin.demo', 'password': secrets.token_urlsafe()}).status_code == 401
        assert client.post('/api/admin/users', json={}).status_code == 401

    chosen_password = secrets.token_urlsafe()
    provision(clean, chosen_password)
    with pytest.raises(ValueError, match='ya está configurada'):
        provision(clean, secrets.token_urlsafe())
    app = create_app(clean, maintenance=False)
    with TestClient(app) as client, app.state.session_factory() as db:
        user = authenticate(client, 'operador.pruebas', chosen_password)
        assert user['role'] == 'admin' and not user['is_demo']
        assert db.scalar(select(func.count()).select_from(User)) == 1
        saved = db.get(User, user['id'])
        assert saved.password_hash != chosen_password and verify(chosen_password, saved.password_hash)
        assert db.scalar(select(CoreState.id).where(CoreState.center_id == saved.center_id))
        assert client.get('/api/admin/users').status_code == 200


def test_concurrent_bootstrap_creates_one_admin(clean):
    app = create_app(clean, maintenance=False)
    app.state.engine.dispose()

    def attempt():
        try:
            provision(clean, secrets.token_urlsafe())
            return True
        except ValueError as exc:
            assert 'ya está configurada' in str(exc)
            return False

    with ThreadPoolExecutor(2) as pool:
        assert sorted(pool.map(lambda _: attempt(), range(2))) == [False, True]


def test_promotion_requires_admin_and_revokes_existing_session(clean):
    chosen_password = secrets.token_urlsafe()
    provision(clean, chosen_password)
    app = create_app(clean, maintenance=False)
    with TestClient(app) as admin, TestClient(app) as student:
        administrator = authenticate(admin, 'operador.pruebas', chosen_password)
        own_password = secrets.token_urlsafe()
        created = admin.post('/api/admin/users', json={'username': 'new.student', 'display_name': 'Alumno ficticio',
                             'password': own_password, 'role': 'student'})
        assert created.status_code == 201 and not created.json()['is_demo']
        target = '/api/admin/users/' + created.json()['id']
        authenticate(student, 'new.student', own_password)
        assert student.patch(target, json={'role': 'admin'}).status_code == 403
        assert student.patch('/api/auth/preferences', json={'role': 'teacher'}).status_code == 422
        assert admin.patch('/api/admin/users/' + administrator['id'], json={'role': 'student'}).status_code == 422
        approved = admin.patch(target, json={'role': 'teacher'})
        assert approved.status_code == 200 and approved.json()['role'] == 'teacher'
        assert student.get('/api/auth/me').status_code == 401
        assert authenticate(student, 'new.student', own_password)['role'] == 'teacher'
        assert student.get('/api/admin/users').status_code == 403
        assert any(row['operation'] == 'user_role_changed' for row in admin.get('/api/admin/audit').json())


def test_local_recovery_revokes_old_sessions(clean):
    original, replacement = secrets.token_urlsafe(), secrets.token_urlsafe()
    provision(clean, original)
    app = create_app(clean, maintenance=False)
    with TestClient(app) as client:
        authenticate(client, 'operador.pruebas', original)
        reset_password(clean, 'operador.pruebas', replacement)
        assert client.get('/api/auth/me').status_code == 401
        assert client.post('/api/auth/login', json={'username': 'operador.pruebas', 'password': original}).status_code == 401
        authenticate(client, 'operador.pruebas', replacement)
        with app.state.session_factory() as db:
            assert db.scalar(select(func.count()).select_from(Session)) == 1


def test_optional_demo_generates_distinct_credentials_in_separate_folder(clean, tmp_path):
    folder = tmp_path / 'demo'
    path = create_local_demo(clean, folder)
    credentials = [line.split(': ', 1)[1] for line in path.read_text().splitlines()]
    assert len(credentials) == len(set(credentials)) == 6
    assert path.stat().st_mode & 0o777 == 0o600
    assert not (clean.data_dir / 'axon.sqlite3').exists()
    app = create_app(demo_profile(clean, folder), maintenance=False)
    with TestClient(app) as client:
        assert authenticate(client, 'admin.demo', credentials[0])['is_demo']
    with pytest.raises(ValueError, match='ya está configurada'):
        create_local_demo(clean, folder)


def test_external_host_requires_exact_https_and_secure_cookie(clean, monkeypatch):
    monkeypatch.setenv('AXON_ALLOWED_HOSTS', 'school.example')
    monkeypatch.setenv('AXON_ALLOWED_ORIGINS', 'https://school.example')
    monkeypatch.setenv('AXON_COOKIE_SECURE', 'false')
    with pytest.raises(ValueError, match='cookies seguras'):
        Settings.from_env()
    monkeypatch.setenv('AXON_COOKIE_SECURE', 'true')
    configured = Settings.from_env()
    password = secrets.token_urlsafe()
    provision(clean, password)
    app = create_app(replace(clean, allowed_hosts=configured.allowed_hosts, allowed_origins=configured.allowed_origins,
                             cookie_secure=True), maintenance=False)
    with TestClient(app, base_url='https://school.example') as client:
        response = client.post('/api/auth/login', json={'username': 'operador.pruebas','password': password})
        cookie = response.headers['set-cookie'].lower()
        assert all(value in cookie for value in ('secure', 'httponly', 'samesite=strict'))
        assert client.get('/api/health', headers={'Host': 'another.example'}).status_code == 400
        assert client.post('/api/auth/logout', headers={'Origin': 'https://another.example'}).status_code == 403
