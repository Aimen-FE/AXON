"""Configuration and teacher-only content for the fictional education scenario."""
from sqlalchemy import Boolean, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base, Identity, UTCDateTime


class GroupTutorship(Identity, Base):
    __tablename__ = 'group_tutorships'
    group_id: Mapped[str] = mapped_column(ForeignKey('groups.id', ondelete='CASCADE'), unique=True)
    teacher_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    classroom_id: Mapped[str] = mapped_column(ForeignKey('classrooms.id'))
    office_hour: Mapped[str] = mapped_column(String(120))


class ClassEvaluation(Identity, Base):
    __tablename__ = 'class_evaluations'
    class_id: Mapped[str] = mapped_column(ForeignKey('learning_classes.id', ondelete='CASCADE'), unique=True)
    weights: Mapped[dict] = mapped_column(JSON)


class ClassSolution(Identity, Base):
    __tablename__ = 'class_solutions'
    activity_id: Mapped[str] = mapped_column(ForeignKey('class_activities.id', ondelete='CASCADE'), unique=True)
    content: Mapped[str] = mapped_column(Text)


class ClassAdmission(Identity, Base):
    __tablename__ = 'class_admissions'
    class_id: Mapped[str] = mapped_column(ForeignKey('learning_classes.id', ondelete='CASCADE'), unique=True)
    teacher_invitations: Mapped[bool] = mapped_column(Boolean, default=True)
    review_codes: Mapped[bool] = mapped_column(Boolean, default=False)
    code_expires_at: Mapped[object | None] = mapped_column(UTCDateTime(), nullable=True)
    code_limit: Mapped[int] = mapped_column(Integer, default=30)
    code_uses: Mapped[int] = mapped_column(Integer, default=0)


class ClassJoinRequest(Identity, Base):
    __tablename__ = 'class_join_requests'
    class_id: Mapped[str] = mapped_column(ForeignKey('learning_classes.id', ondelete='CASCADE'))
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'))
    status: Mapped[str] = mapped_column(String(12), default='pending')
    __table_args__ = (UniqueConstraint('class_id', 'user_id'),)
