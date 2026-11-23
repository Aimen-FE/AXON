import asyncio
import secrets
from dataclasses import replace

import httpx

from app.config import Settings
from app.main import create_app

PAGES = 'https://axon-public.example.org'
WORKSPACE = 'https://workspace.example.org'


def test_public_probe_has_exact_origin_and_auth_remains_same_origin(tmp_path):
    settings = replace(Settings.from_env(), data_dir=tmp_path,
                       database_url=f'sqlite:///{tmp_path}/test.sqlite3', demo=True, ai_mode='simulated',
                       cookie_secure=True, pages_origin=PAGES, allowed_origins=(WORKSPACE,),
                       allowed_hosts=('workspace.example.org',))
    password = secrets.token_urlsafe(24)
    application = create_app(settings, maintenance=False, demo_passwords={'alumno.demo': password})

    async def check():
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(transport=transport, base_url=WORKSPACE, follow_redirects=False) as client:
            probe = await client.get('/api/public/connection', headers={'Origin': PAGES})
            assert probe.status_code == 200
            assert probe.json() == {'service': 'axon', 'status': 'ok',
                                    'version': application.version, 'auth': 'same-origin'}
            assert probe.headers['access-control-allow-origin'] == PAGES
            assert probe.headers['vary'] == 'Origin'
            assert probe.headers['cache-control'] == 'no-store'
            assert 'set-cookie' not in probe.headers
            assert 'access-control-allow-credentials' not in probe.headers
            foreign = await client.get('/api/public/connection', headers={'Origin': PAGES + '.wrong.example.org'})
            assert foreign.status_code == 403 and 'access-control-allow-origin' not in foreign.headers
            assert (await client.get('/api/public/connection')).status_code == 200
            unauthorized = await client.get('/api/auth/me', headers={'Origin': PAGES})
            assert unauthorized.status_code == 401 and 'access-control-allow-origin' not in unauthorized.headers

            payload = {'username': 'alumno.demo', 'password': password}
            denied = await client.post('/api/auth/login', headers={'Origin': PAGES}, json=payload)
            assert denied.status_code == 403 and 'set-cookie' not in denied.headers
            login = await client.post('/api/auth/login', headers={'Origin': WORKSPACE}, json=payload)
            assert login.status_code == 200
            header = login.headers['set-cookie'].lower()
            assert all(flag in header for flag in ('httponly', 'secure', 'samesite=strict'))
            authenticated = await client.get('/api/auth/me')
            assert authenticated.json()['user']['username'] == 'alumno.demo'
            assert (await client.post('/api/auth/logout', headers={'Origin': WORKSPACE})).status_code == 403
            csrf = login.json()['csrf_token']
            assert (await client.post('/api/auth/logout', headers={'Origin': WORKSPACE, 'X-CSRF-Token': csrf})).status_code == 200

    try:
        asyncio.run(check())
    finally:
        application.state.engine.dispose()


def test_probe_disabled_by_default(tmp_path):
    settings = replace(Settings.from_env(), data_dir=tmp_path,
                       database_url=f'sqlite:///{tmp_path}/test.sqlite3', demo=False, pages_origin='')
    application = create_app(settings, maintenance=False)

    async def check():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=application), base_url='http://testserver') as client:
            response = await client.get('/api/public/connection', headers={'Origin': PAGES})
            assert response.status_code == 404
            assert 'access-control-allow-origin' not in response.headers

    try:
        asyncio.run(check())
    finally:
        application.state.engine.dispose()
