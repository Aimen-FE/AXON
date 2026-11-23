"""Isolated full-application teacher sessions, additive only."""
from alembic import op
import sqlalchemy as sa
revision='0006'
down_revision='0005'
branch_labels=None
depends_on=None

def upgrade():
    op.create_index('ix_guest_rates_window','guest_rates',['key_hash','created_at'])
    op.create_table('teacher_demo_sessions',sa.Column('id',sa.String(36),primary_key=True),sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),sa.Column('updated_at',sa.DateTime(timezone=True),nullable=False),sa.Column('user_id',sa.String(36),sa.ForeignKey('users.id',ondelete='CASCADE'),nullable=False,unique=True),sa.Column('center_id',sa.String(36),sa.ForeignKey('centers.id'),nullable=False,unique=True),sa.Column('expires_at',sa.DateTime(timezone=True),nullable=False),sa.Column('last_seen_at',sa.DateTime(timezone=True),nullable=False),sa.Column('request_count',sa.Integer(),nullable=False),sa.Column('revoked',sa.Boolean(),nullable=False))
    for field in ('user_id','center_id','expires_at'):op.create_index('ix_teacher_demo_sessions_'+field,'teacher_demo_sessions',[field])
def downgrade():raise RuntimeError('Restaurar una copia verificada; no eliminar sesiones por downgrade')
