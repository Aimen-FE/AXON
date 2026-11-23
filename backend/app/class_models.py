"""Native classes. Academic structure, identities, documents and events are shared with AXON."""
from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base, Identity, UTCDateTime


class LearningClass(Identity, Base):
    __tablename__ = 'learning_classes'
    center_id: Mapped[str] = mapped_column(ForeignKey('centers.id'), index=True)
    group_id: Mapped[str] = mapped_column(ForeignKey('groups.id'))
    subject_id: Mapped[str] = mapped_column(ForeignKey('subjects.id'))
    creator_id: Mapped[str | None] = mapped_column(ForeignKey('users.id', ondelete='SET NULL'))
    name: Mapped[str] = mapped_column(String(140))
    description: Mapped[str] = mapped_column(Text, default='')
    color: Mapped[str] = mapped_column(String(16), default='mint')
    archived: Mapped[bool] = mapped_column(Boolean, default=False)
    join_hash: Mapped[str | None] = mapped_column(String(64), unique=True)


class ClassMember(Identity, Base):
    __tablename__ = 'class_members'
    class_id: Mapped[str] = mapped_column(ForeignKey('learning_classes.id', ondelete='CASCADE'))
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    role: Mapped[str] = mapped_column(String(12))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    __table_args__ = (UniqueConstraint('class_id', 'user_id'), CheckConstraint("role IN ('teacher', 'student')"))


class ClassInvitation(Identity, Base):
    __tablename__ = 'class_invitations'
    class_id: Mapped[str] = mapped_column(ForeignKey('learning_classes.id', ondelete='CASCADE'))
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    expires_at: Mapped[object] = mapped_column(UTCDateTime())
    __table_args__ = (UniqueConstraint('class_id', 'user_id'),)


class ClassPost(Identity, Base):
    __tablename__ = 'class_posts'
    class_id: Mapped[str] = mapped_column(ForeignKey('learning_classes.id', ondelete='CASCADE'), index=True)
    author_id: Mapped[str | None] = mapped_column(ForeignKey('users.id', ondelete='SET NULL'))
    title: Mapped[str] = mapped_column(String(160))
    content: Mapped[str] = mapped_column(Text)
    pinned: Mapped[bool] = mapped_column(Boolean, default=False)
    comments_open: Mapped[bool] = mapped_column(Boolean, default=False)
    hidden: Mapped[bool] = mapped_column(Boolean, default=False)


class ClassComment(Identity, Base):
    __tablename__ = 'class_comments'
    post_id: Mapped[str] = mapped_column(ForeignKey('class_posts.id', ondelete='CASCADE'), index=True)
    author_id: Mapped[str | None] = mapped_column(ForeignKey('users.id', ondelete='SET NULL'))
    content: Mapped[str] = mapped_column(Text)
    hidden: Mapped[bool] = mapped_column(Boolean, default=False)


class ClassTopic(Identity, Base):
    __tablename__ = 'class_topics'
    class_id: Mapped[str] = mapped_column(ForeignKey('learning_classes.id', ondelete='CASCADE'))
    name: Mapped[str] = mapped_column(String(100))
    __table_args__ = (UniqueConstraint('class_id', 'name'),)


class ClassTeam(Identity, Base):
    __tablename__ = 'class_teams'
    class_id: Mapped[str] = mapped_column(ForeignKey('learning_classes.id', ondelete='CASCADE'))
    name: Mapped[str] = mapped_column(String(100))
    __table_args__ = (UniqueConstraint('class_id', 'name'),)


class ClassTeamMember(Identity, Base):
    __tablename__ = 'class_team_members'
    team_id: Mapped[str] = mapped_column(ForeignKey('class_teams.id', ondelete='CASCADE'), index=True)
    class_id: Mapped[str] = mapped_column(ForeignKey('learning_classes.id', ondelete='CASCADE'))
    student_id: Mapped[str] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    __table_args__ = (UniqueConstraint('class_id', 'student_id'),)


class ClassActivity(Identity, Base):
    __tablename__ = 'class_activities'
    class_id: Mapped[str] = mapped_column(ForeignKey('learning_classes.id', ondelete='CASCADE'), index=True)
    topic_id: Mapped[str | None] = mapped_column(ForeignKey('class_topics.id', ondelete='SET NULL'))
    creator_id: Mapped[str | None] = mapped_column(ForeignKey('users.id', ondelete='SET NULL'))
    title: Mapped[str] = mapped_column(String(160))
    instructions: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String(12))
    delivery: Mapped[str] = mapped_column(String(12))
    due_at: Mapped[object | None] = mapped_column(UTCDateTime(), index=True)
    exam_at: Mapped[object | None] = mapped_column(UTCDateTime())
    exam_minutes: Mapped[int] = mapped_column(Integer, default=60)
    max_points: Mapped[int | None] = mapped_column(Integer)
    questions: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(12), default='draft')
    __table_args__ = (
        CheckConstraint("kind IN ('task', 'exercise', 'quiz', 'project', 'exam')"),
        CheckConstraint("delivery IN ('individual', 'team')"),
        CheckConstraint("status IN ('draft', 'published', 'closed')"),
        CheckConstraint('max_points IS NULL OR max_points > 0'),
    )


class ClassRubric(Identity, Base):
    __tablename__ = 'class_rubrics'
    activity_id: Mapped[str] = mapped_column(ForeignKey('class_activities.id', ondelete='CASCADE'), unique=True)
    criteria: Mapped[list] = mapped_column(JSON)


class ClassSubmission(Identity, Base):
    __tablename__ = 'class_submissions'
    activity_id: Mapped[str] = mapped_column(ForeignKey('class_activities.id', ondelete='CASCADE'))
    student_id: Mapped[str | None] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    team_id: Mapped[str | None] = mapped_column(ForeignKey('class_teams.id', ondelete='CASCADE'))
    content: Mapped[str] = mapped_column(Text, default='')
    answers: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(12), default='draft')
    version: Mapped[int] = mapped_column(Integer, default=0)
    submitted_at: Mapped[object | None] = mapped_column(UTCDateTime())
    __table_args__ = (
        UniqueConstraint('activity_id', 'student_id'),
        UniqueConstraint('activity_id', 'team_id'),
        CheckConstraint('(student_id IS NULL) != (team_id IS NULL)'),
        CheckConstraint("status IN ('draft', 'submitted', 'returned')"),
    )


class ClassGrade(Identity, Base):
    __tablename__ = 'class_grades'
    submission_id: Mapped[str] = mapped_column(ForeignKey('class_submissions.id', ondelete='CASCADE'), unique=True)
    reviewer_id: Mapped[str | None] = mapped_column(ForeignKey('users.id', ondelete='SET NULL'))
    points: Mapped[int | None] = mapped_column(Integer)
    feedback: Mapped[str] = mapped_column(Text, default='')
    criteria_scores: Mapped[list] = mapped_column(JSON, default=list)


class ClassSubmissionRevision(Identity, Base):
    __tablename__ = 'class_submission_revisions'
    submission_id: Mapped[str] = mapped_column(ForeignKey('class_submissions.id', ondelete='CASCADE'))
    author_id: Mapped[str | None] = mapped_column(ForeignKey('users.id', ondelete='SET NULL'))
    version: Mapped[int] = mapped_column(Integer)
    change: Mapped[str] = mapped_column(String(24))
    snapshot: Mapped[dict] = mapped_column(JSON)
    __table_args__ = (UniqueConstraint('submission_id', 'version'),)


class ClassFile(Identity, Base):
    __tablename__ = 'class_files'
    class_id: Mapped[str] = mapped_column(ForeignKey('learning_classes.id', ondelete='CASCADE'), index=True)
    document_id: Mapped[str] = mapped_column(ForeignKey('documents.id', ondelete='CASCADE'), unique=True)
    topic_id: Mapped[str | None] = mapped_column(ForeignKey('class_topics.id', ondelete='SET NULL'))
    activity_id: Mapped[str | None] = mapped_column(ForeignKey('class_activities.id', ondelete='CASCADE'), index=True)
    submission_id: Mapped[str | None] = mapped_column(ForeignKey('class_submissions.id', ondelete='CASCADE'), index=True)
    hidden: Mapped[bool] = mapped_column(Boolean, default=False)
    __table_args__ = (CheckConstraint('activity_id IS NULL OR submission_id IS NULL'),)


class ClassEvent(Identity, Base):
    __tablename__ = 'class_events'
    class_id: Mapped[str] = mapped_column(ForeignKey('learning_classes.id', ondelete='CASCADE'), index=True)
    event_id: Mapped[str] = mapped_column(ForeignKey('calendar_events.id', ondelete='CASCADE'), unique=True)
    activity_id: Mapped[str | None] = mapped_column(ForeignKey('class_activities.id', ondelete='CASCADE'))
    purpose: Mapped[str] = mapped_column(String(12), default='event')
    __table_args__ = (
        UniqueConstraint('activity_id', 'purpose'),
        CheckConstraint("purpose IN ('event', 'deadline', 'exam')"),
    )
