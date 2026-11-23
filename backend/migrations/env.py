from alembic import context
from sqlalchemy import create_engine
from app.config import Settings
from app.db import Base
from app import models  # noqa: F401

config = context.config
metadata = Base.metadata
url = config.attributes.get('database_url') or Settings.from_env().database_url
if context.is_offline_mode():
    context.configure(url=url, target_metadata=metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    engine = create_engine(url)
    with engine.connect() as connection:
        if engine.dialect.name == 'sqlite':
            connection.exec_driver_sql('PRAGMA foreign_keys=ON')
            connection.commit()
        context.configure(connection=connection, target_metadata=metadata, render_as_batch=engine.dialect.name == 'sqlite')
        with context.begin_transaction():
            context.run_migrations()
