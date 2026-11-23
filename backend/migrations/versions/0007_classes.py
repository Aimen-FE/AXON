"""Add native classes without rewriting existing tables."""
from alembic import op
import sqlalchemy as sa

revision = '0007'
down_revision = '0006'
branch_labels = None
depends_on = None

def upgrade():
    op.create_table('learning_classes',
    sa.Column('center_id', sa.String(length=36), nullable=False),
    sa.Column('group_id', sa.String(length=36), nullable=False),
    sa.Column('subject_id', sa.String(length=36), nullable=False),
    sa.Column('creator_id', sa.String(length=36), nullable=True),
    sa.Column('name', sa.String(length=140), nullable=False),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('color', sa.String(length=16), nullable=False),
    sa.Column('archived', sa.Boolean(), nullable=False),
    sa.Column('join_hash', sa.String(length=64), nullable=True),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['center_id'], ['centers.id'], ),
    sa.ForeignKeyConstraint(['creator_id'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['group_id'], ['groups.id'], ),
    sa.ForeignKeyConstraint(['subject_id'], ['subjects.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('join_hash')
    )
    op.create_table('class_invitations',
    sa.Column('class_id', sa.String(length=36), nullable=False),
    sa.Column('user_id', sa.String(length=36), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['class_id'], ['learning_classes.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('class_id', 'user_id')
    )
    op.create_table('class_members',
    sa.Column('class_id', sa.String(length=36), nullable=False),
    sa.Column('user_id', sa.String(length=36), nullable=False),
    sa.Column('role', sa.String(length=12), nullable=False),
    sa.Column('active', sa.Boolean(), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("role IN ('teacher', 'student')"),
    sa.ForeignKeyConstraint(['class_id'], ['learning_classes.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('class_id', 'user_id')
    )
    op.create_table('class_posts',
    sa.Column('class_id', sa.String(length=36), nullable=False),
    sa.Column('author_id', sa.String(length=36), nullable=True),
    sa.Column('title', sa.String(length=160), nullable=False),
    sa.Column('content', sa.Text(), nullable=False),
    sa.Column('pinned', sa.Boolean(), nullable=False),
    sa.Column('comments_open', sa.Boolean(), nullable=False),
    sa.Column('hidden', sa.Boolean(), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['author_id'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['class_id'], ['learning_classes.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('class_teams',
    sa.Column('class_id', sa.String(length=36), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['class_id'], ['learning_classes.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('class_id', 'name')
    )
    op.create_table('class_topics',
    sa.Column('class_id', sa.String(length=36), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['class_id'], ['learning_classes.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('class_id', 'name')
    )
    op.create_table('class_activities',
    sa.Column('class_id', sa.String(length=36), nullable=False),
    sa.Column('topic_id', sa.String(length=36), nullable=True),
    sa.Column('creator_id', sa.String(length=36), nullable=True),
    sa.Column('title', sa.String(length=160), nullable=False),
    sa.Column('instructions', sa.Text(), nullable=False),
    sa.Column('kind', sa.String(length=12), nullable=False),
    sa.Column('delivery', sa.String(length=12), nullable=False),
    sa.Column('due_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('exam_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('exam_minutes', sa.Integer(), nullable=False),
    sa.Column('max_points', sa.Integer(), nullable=True),
    sa.Column('questions', sa.JSON(), nullable=False),
    sa.Column('status', sa.String(length=12), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("delivery IN ('individual', 'team')"),
    sa.CheckConstraint("kind IN ('task', 'exercise', 'quiz', 'project', 'exam')"),
    sa.CheckConstraint("status IN ('draft', 'published', 'closed')"),
    sa.CheckConstraint('max_points IS NULL OR max_points > 0'),
    sa.ForeignKeyConstraint(['class_id'], ['learning_classes.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['creator_id'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['topic_id'], ['class_topics.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('class_comments',
    sa.Column('post_id', sa.String(length=36), nullable=False),
    sa.Column('author_id', sa.String(length=36), nullable=True),
    sa.Column('content', sa.Text(), nullable=False),
    sa.Column('hidden', sa.Boolean(), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['author_id'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['post_id'], ['class_posts.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('class_team_members',
    sa.Column('team_id', sa.String(length=36), nullable=False),
    sa.Column('class_id', sa.String(length=36), nullable=False),
    sa.Column('student_id', sa.String(length=36), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['class_id'], ['learning_classes.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['student_id'], ['users.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['team_id'], ['class_teams.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('class_id', 'student_id')
    )
    op.create_table('class_events',
    sa.Column('class_id', sa.String(length=36), nullable=False),
    sa.Column('event_id', sa.String(length=36), nullable=False),
    sa.Column('activity_id', sa.String(length=36), nullable=True),
    sa.Column('purpose', sa.String(length=12), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("purpose IN ('event', 'deadline', 'exam')"),
    sa.ForeignKeyConstraint(['activity_id'], ['class_activities.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['class_id'], ['learning_classes.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['event_id'], ['calendar_events.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('activity_id', 'purpose'),
    sa.UniqueConstraint('event_id')
    )
    op.create_table('class_rubrics',
    sa.Column('activity_id', sa.String(length=36), nullable=False),
    sa.Column('criteria', sa.JSON(), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['activity_id'], ['class_activities.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('activity_id')
    )
    op.create_table('class_submissions',
    sa.Column('activity_id', sa.String(length=36), nullable=False),
    sa.Column('student_id', sa.String(length=36), nullable=True),
    sa.Column('team_id', sa.String(length=36), nullable=True),
    sa.Column('content', sa.Text(), nullable=False),
    sa.Column('answers', sa.JSON(), nullable=False),
    sa.Column('status', sa.String(length=12), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('submitted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("status IN ('draft', 'submitted', 'returned')"),
    sa.CheckConstraint('(student_id IS NULL) != (team_id IS NULL)'),
    sa.ForeignKeyConstraint(['activity_id'], ['class_activities.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['student_id'], ['users.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['team_id'], ['class_teams.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('activity_id', 'student_id'),
    sa.UniqueConstraint('activity_id', 'team_id')
    )
    op.create_table('class_files',
    sa.Column('class_id', sa.String(length=36), nullable=False),
    sa.Column('document_id', sa.String(length=36), nullable=False),
    sa.Column('topic_id', sa.String(length=36), nullable=True),
    sa.Column('activity_id', sa.String(length=36), nullable=True),
    sa.Column('submission_id', sa.String(length=36), nullable=True),
    sa.Column('hidden', sa.Boolean(), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint('activity_id IS NULL OR submission_id IS NULL'),
    sa.ForeignKeyConstraint(['activity_id'], ['class_activities.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['class_id'], ['learning_classes.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['document_id'], ['documents.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['submission_id'], ['class_submissions.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['topic_id'], ['class_topics.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('document_id')
    )
    op.create_table('class_grades',
    sa.Column('submission_id', sa.String(length=36), nullable=False),
    sa.Column('reviewer_id', sa.String(length=36), nullable=True),
    sa.Column('points', sa.Integer(), nullable=True),
    sa.Column('feedback', sa.Text(), nullable=False),
    sa.Column('criteria_scores', sa.JSON(), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['reviewer_id'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['submission_id'], ['class_submissions.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('submission_id')
    )
    op.create_table('class_submission_revisions',
    sa.Column('submission_id', sa.String(length=36), nullable=False),
    sa.Column('author_id', sa.String(length=36), nullable=True),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('change', sa.String(length=24), nullable=False),
    sa.Column('snapshot', sa.JSON(), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['author_id'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['submission_id'], ['class_submissions.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('submission_id', 'version')
    )
    op.create_index(op.f('ix_learning_classes_center_id'), 'learning_classes', ['center_id'], unique=False)
    op.create_index(op.f('ix_class_invitations_user_id'), 'class_invitations', ['user_id'], unique=False)
    op.create_index(op.f('ix_class_members_user_id'), 'class_members', ['user_id'], unique=False)
    op.create_index(op.f('ix_class_posts_class_id'), 'class_posts', ['class_id'], unique=False)
    op.create_index(op.f('ix_class_activities_class_id'), 'class_activities', ['class_id'], unique=False)
    op.create_index(op.f('ix_class_activities_due_at'), 'class_activities', ['due_at'], unique=False)
    op.create_index(op.f('ix_class_comments_post_id'), 'class_comments', ['post_id'], unique=False)
    op.create_index(op.f('ix_class_team_members_student_id'), 'class_team_members', ['student_id'], unique=False)
    op.create_index(op.f('ix_class_team_members_team_id'), 'class_team_members', ['team_id'], unique=False)
    op.create_index(op.f('ix_class_events_class_id'), 'class_events', ['class_id'], unique=False)
    op.create_index(op.f('ix_class_submissions_student_id'), 'class_submissions', ['student_id'], unique=False)
    op.create_index(op.f('ix_class_files_activity_id'), 'class_files', ['activity_id'], unique=False)
    op.create_index(op.f('ix_class_files_class_id'), 'class_files', ['class_id'], unique=False)
    op.create_index(op.f('ix_class_files_submission_id'), 'class_files', ['submission_id'], unique=False)


def downgrade():
    raise RuntimeError('Restaura una copia anterior para conservar los datos de Clases')
