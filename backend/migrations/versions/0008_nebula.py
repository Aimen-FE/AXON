"""Add class admission, evaluation and tutor configuration."""
from alembic import op
import sqlalchemy as sa

revision="0008"
down_revision="0007"
branch_labels=None
depends_on=None

def upgrade():
    op.create_table('group_tutorships',
    sa.Column('group_id', sa.String(length=36), nullable=False),
    sa.Column('teacher_id', sa.String(length=36), nullable=False),
    sa.Column('classroom_id', sa.String(length=36), nullable=False),
    sa.Column('office_hour', sa.String(length=120), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['classroom_id'], ['classrooms.id'], ),
    sa.ForeignKeyConstraint(['group_id'], ['groups.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['teacher_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('group_id')
    )
    op.create_table('class_admissions',
    sa.Column('class_id', sa.String(length=36), nullable=False),
    sa.Column('teacher_invitations', sa.Boolean(), nullable=False),
    sa.Column('review_codes', sa.Boolean(), nullable=False),
    sa.Column('code_expires_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('code_limit', sa.Integer(), nullable=False),
    sa.Column('code_uses', sa.Integer(), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['class_id'], ['learning_classes.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('class_id')
    )
    op.create_table('class_evaluations',
    sa.Column('class_id', sa.String(length=36), nullable=False),
    sa.Column('weights', sa.JSON(), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['class_id'], ['learning_classes.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('class_id')
    )
    op.create_table('class_join_requests',
    sa.Column('class_id', sa.String(length=36), nullable=False),
    sa.Column('user_id', sa.String(length=36), nullable=False),
    sa.Column('status', sa.String(length=12), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['class_id'], ['learning_classes.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('class_id', 'user_id')
    )
    op.create_table('class_solutions',
    sa.Column('activity_id', sa.String(length=36), nullable=False),
    sa.Column('content', sa.Text(), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['activity_id'], ['class_activities.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('activity_id')
    )

def downgrade():
    raise RuntimeError("Restaura una copia verificada para conservar los datos")
