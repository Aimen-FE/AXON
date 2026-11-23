"""First administrator, local recovery, and optional fictitious accounts."""
import os
import secrets
import sys
from contextlib import contextmanager
from dataclasses import replace
from getpass import getpass
from pathlib import Path

from sqlalchemy import delete, select, text
from sqlalchemy.engine import make_url

from .atlas import bootstrap
from .auth import ph
from .db import create_db
from .models import AccountSetup, Center, Session, User
from .operations import storage_lock
from .policy import audit
from .schemas import UserCreate
from .seed import DEMO_ACCOUNTS, seed_demo


@contextmanager
def local_database(settings, *, initialize=False):
    if settings.public_demo or settings.remote_demo or settings.full_demo:
        raise ValueError('Usa este asistente desde una instalación local.')
    if not settings.database_url.startswith('sqlite:'):
        raise ValueError('El asistente de instalación admite SQLite.')
    if not initialize and not Path(make_url(settings.database_url).database).is_file():
        raise ValueError('La base todavía no está preparada. Ejecuta primero el asistente setup-admin.')
    settings.data_dir.mkdir(parents=True, mode=0o700, exist_ok=True)
    (settings.data_dir / 'uploads').mkdir(mode=0o700, exist_ok=True)
    with storage_lock(settings):
        if initialize:
            from .main import migrate
            migrate(settings)
        engine, factory = create_db(settings.database_url)
        try:
            with factory() as db:
                db.execute(text('BEGIN IMMEDIATE'))
                yield db
        finally:
            engine.dispose()


def require_empty(db):
    if db.scalar(select(Center.id).limit(1)) or db.scalar(select(User.id).limit(1)):
        raise ValueError('La base ya está configurada. Inicia sesión o utiliza reset-access.')


def create_first_admin(settings, center_name, town, username, display_name, password):
    account = UserCreate(username=username.lower(), display_name=display_name, role='admin', password=password)
    center_name, town = center_name.strip(), town.strip()
    if not 5 <= len(center_name) <= 160 or (town and not 2 <= len(town) <= 100):
        raise ValueError('Indica un nombre de centro de 5 a 160 caracteres. Si añades una localidad, usa entre 2 y 100.')
    with local_database(settings, initialize=True) as db:
        require_empty(db)
        center = Center(name=center_name, town=town or "Sin indicar",
                        settings={'bathroom_retention_days': 14, 'automation_enabled': False})
        db.add(center)
        db.flush()
        user = User(center_id=center.id, username=account.username, display_name=account.display_name,
                    password_hash=ph.hash(account.password), role='admin', active=True, is_demo=False,
                    preferences={'theme': 'dark', 'notifications': {}, 'automatic_personal_actions': False})
        db.add(user)
        db.flush()
        bootstrap(db)
        audit(db, user, 'initial_admin_configured', user)
        db.commit()


def reset_password(settings, username, password):
    if not 12 <= len(password.strip()) <= 128:
        raise ValueError('La contraseña debe tener entre 12 y 128 caracteres.')
    with local_database(settings) as db:
        user = db.scalar(select(User).where(User.username == username.strip().lower(), User.active.is_(True)))
        if not user:
            raise ValueError('No se ha encontrado una cuenta activa con ese usuario.')
        user.password_hash = ph.hash(password.strip())
        db.execute(delete(Session).where(Session.user_id == user.id))
        db.execute(delete(AccountSetup).where(AccountSetup.user_id == user.id))
        audit(db, user, 'password_reset_by_local_operator', user)
        db.commit()


def demo_profile(settings, data_dir):
    folder = Path(data_dir).resolve()
    if folder == settings.data_dir.resolve() or (folder / 'remote-demo.json').exists():
        raise ValueError('Usa una carpeta independiente para la base ficticia.')
    return replace(settings, data_dir=folder, database_url=f'sqlite:///{folder / "axon.sqlite3"}', demo=True)


def create_local_demo(settings, data_dir):
    settings = demo_profile(settings, data_dir)
    passwords = {username: secrets.token_urlsafe(24) for username, _, _ in DEMO_ACCOUNTS}
    credentials = settings.data_dir / 'demo-credentials.txt'
    with local_database(settings, initialize=True) as db:
        require_empty(db)
        seed_demo(db, settings, passwords)
        from .nebula import populate
        populate(db, settings)
        bootstrap(db)
        descriptor = os.open(credentials, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        try:
            with os.fdopen(descriptor, 'w') as stream:
                for username, _, role in DEMO_ACCOUNTS:
                    stream.write(f'{username} ({role}): {passwords[username]}\n')
            db.commit()
        except BaseException:
            credentials.unlink(missing_ok=True)
            raise
    return credentials


def prompt_password():
    if not sys.stdin.isatty() or not sys.stderr.isatty():
        raise ValueError('Abre una terminal interactiva para escribir la contraseña sin mostrarla.')
    password = getpass('Contraseña (12 a 128 caracteres): ').strip()
    if not 12 <= len(password) <= 128:
        raise ValueError('La contraseña debe tener entre 12 y 128 caracteres.')
    if password != getpass('Repite la contraseña: ').strip():
        raise ValueError('Las contraseñas no coinciden.')
    return password
