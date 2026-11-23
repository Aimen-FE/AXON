"""Temporary guests and bounded persistent abuse counters (additive)."""
from alembic import op
import sqlalchemy as sa
revision='0005'
down_revision='0004'
branch_labels=None
depends_on=None

def ident():return [sa.Column('id',sa.String(36),primary_key=True),sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),sa.Column('updated_at',sa.DateTime(timezone=True),nullable=False)]
def upgrade():
    op.create_table('guest_sessions',*ident(),sa.Column('user_id',sa.String(36),sa.ForeignKey('users.id',ondelete='CASCADE'),nullable=False,unique=True),sa.Column('ip_hash',sa.String(64),nullable=False,index=True),sa.Column('expires_at',sa.DateTime(timezone=True),nullable=False,index=True),sa.Column('request_count',sa.Integer(),nullable=False),sa.Column('last_seen_at',sa.DateTime(timezone=True),nullable=False),sa.Column('revoked',sa.Boolean(),nullable=False))
    op.create_index('ix_guest_sessions_user_id','guest_sessions',['user_id'])
    op.create_table('guest_rates',*ident(),sa.Column('key_hash',sa.String(64),nullable=False,index=True))
def downgrade():raise RuntimeError('Restaurar una copia verificada; no borrar sesiones mediante downgrade')
