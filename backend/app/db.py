from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import create_engine, event, DateTime, String
from sqlalchemy.orm import DeclarativeBase, sessionmaker, Mapped, mapped_column
from sqlalchemy.types import TypeDecorator


def utcnow():
    return datetime.now(timezone.utc)


def new_id():
    return str(uuid4())


class UTCDateTime(TypeDecorator):
    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is not None:
            if value.tzinfo is None:
                raise ValueError('Se requiere fecha con zona horaria')
            return value.astimezone(timezone.utc)
        return value

    def process_result_value(self, value, dialect):
        if value is not None:
            return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
        return value


class Base(DeclarativeBase):
    pass


class Identity:
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    created_at: Mapped[object] = mapped_column(UTCDateTime(), default=utcnow)
    updated_at: Mapped[object] = mapped_column(UTCDateTime(), default=utcnow, onupdate=utcnow)


def create_db(url):
    kw = {'check_same_thread': False, 'timeout': 20} if url.startswith('sqlite') else {}
    engine = create_engine(url, connect_args=kw, pool_pre_ping=True)
    if url.startswith('sqlite'):
        @event.listens_for(engine, 'connect')
        def sqlite_config(conn, _):
            conn.execute('PRAGMA foreign_keys=ON')
            conn.execute('PRAGMA journal_mode=WAL')
            conn.execute('PRAGMA busy_timeout=20000')
    return engine, sessionmaker(engine, expire_on_commit=False)
