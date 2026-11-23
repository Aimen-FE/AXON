"""Trusted core, provenance, runtime policies and isolated invitations (additive)."""
from alembic import op
import sqlalchemy as sa
revision='0004'
down_revision='0003'
branch_labels=None
depends_on=None

def identity():
    return [sa.Column('id',sa.String(36),primary_key=True),sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),sa.Column('updated_at',sa.DateTime(timezone=True),nullable=False)]

def upgrade():
    op.create_table('core_states',*identity(),sa.Column('center_id',sa.String(36),sa.ForeignKey('centers.id'),nullable=False,unique=True),sa.Column('version',sa.Integer(),nullable=False),sa.Column('payload',sa.JSON(),nullable=False))
    op.create_table('core_revisions',*identity(),sa.Column('center_id',sa.String(36),sa.ForeignKey('centers.id'),nullable=False,index=True),sa.Column('version',sa.Integer(),nullable=False),sa.Column('payload',sa.JSON(),nullable=False),sa.Column('actor_id',sa.String(36),sa.ForeignKey('users.id',ondelete='SET NULL')),sa.Column('reason',sa.String(300),nullable=False),sa.UniqueConstraint('center_id','version'))
    op.create_table('institutional_sources',*identity(),sa.Column('center_id',sa.String(36),sa.ForeignKey('centers.id'),nullable=False,index=True),sa.Column('document_id',sa.String(36),sa.ForeignKey('documents.id',ondelete='CASCADE'),nullable=False,unique=True),sa.Column('source_url',sa.String(1200),nullable=False),sa.Column('category',sa.String(50),nullable=False),sa.Column('published_on',sa.String(30)),sa.Column('checked_on',sa.String(30),nullable=False),sa.Column('academic_year',sa.String(30)),sa.Column('verification',sa.String(30),nullable=False),sa.Column('applicability',sa.String(30),nullable=False),sa.Column('authority',sa.String(40),nullable=False),sa.Column('notes',sa.Text(),nullable=False))
    op.create_table('provider_policies',*identity(),sa.Column('center_id',sa.String(36),sa.ForeignKey('centers.id'),nullable=False,unique=True),sa.Column('version',sa.Integer(),nullable=False),sa.Column('payload',sa.JSON(),nullable=False))
    op.create_table('remote_invitations',*identity(),sa.Column('user_id',sa.String(36),sa.ForeignKey('users.id',ondelete='CASCADE'),nullable=False,unique=True),sa.Column('email',sa.String(254),nullable=False,unique=True),sa.Column('token_hash',sa.String(64),nullable=False,unique=True),sa.Column('expires_at',sa.DateTime(timezone=True),nullable=False),sa.Column('consumed',sa.Boolean(),nullable=False),sa.Column('revoked',sa.Boolean(),nullable=False))

def downgrade():
    raise RuntimeError('Restaurar una copia verificada: no se borran datos de ATLAS mediante downgrade')
