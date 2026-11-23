from sqlalchemy import String, Text, Integer, Boolean, ForeignKey, JSON, UniqueConstraint, CheckConstraint, Index, text
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base, UTCDateTime, utcnow, new_id, Identity


class Center(Identity, Base):
    __tablename__ = 'centers'
    name: Mapped[str] = mapped_column(String(160))
    town: Mapped[str] = mapped_column(String(100), default='Villa Prisma')
    timezone: Mapped[str] = mapped_column(String(50), default='Europe/Madrid')
    settings: Mapped[dict] = mapped_column(JSON, default=dict)


class AcademicYear(Identity, Base):
    __tablename__ = 'academic_years'
    center_id: Mapped[str] = mapped_column(ForeignKey('centers.id'))
    name: Mapped[str] = mapped_column(String(20))
    __table_args__ = (UniqueConstraint('center_id', 'name'),)


class Course(Identity, Base):
    __tablename__ = 'courses'
    center_id: Mapped[str] = mapped_column(ForeignKey('centers.id'))
    year_id: Mapped[str] = mapped_column(ForeignKey('academic_years.id'))
    name: Mapped[str] = mapped_column(String(100))
    stage: Mapped[str] = mapped_column(String(50))


class Group(Identity, Base):
    __tablename__ = 'groups'
    center_id: Mapped[str] = mapped_column(ForeignKey('centers.id'))
    course_id: Mapped[str] = mapped_column(ForeignKey('courses.id'))
    name: Mapped[str] = mapped_column(String(100))
    __table_args__ = (UniqueConstraint('center_id', 'name'),)


class Subject(Identity, Base):
    __tablename__ = 'subjects'
    center_id: Mapped[str] = mapped_column(ForeignKey('centers.id'))
    name: Mapped[str] = mapped_column(String(100))
    color: Mapped[str] = mapped_column(String(20), default='#137f76')
    __table_args__ = (UniqueConstraint('center_id', 'name'),)


class Classroom(Identity, Base):
    __tablename__ = 'classrooms'
    center_id: Mapped[str] = mapped_column(ForeignKey('centers.id'))
    name: Mapped[str] = mapped_column(String(80))


class User(Identity, Base):
    __tablename__ = 'users'
    center_id: Mapped[str] = mapped_column(ForeignKey('centers.id'), index=True)
    username: Mapped[str] = mapped_column(String(100), unique=True)
    display_name: Mapped[str] = mapped_column(String(100))
    password_hash: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(String(20))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    preferences: Mapped[dict] = mapped_column(JSON, default=dict)
    __table_args__ = (CheckConstraint("role IN ('student','teacher','admin')"),)


class Enrollment(Identity, Base):
    __tablename__ = 'enrollments'
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'))
    group_id: Mapped[str] = mapped_column(ForeignKey('groups.id'))
    __table_args__ = (UniqueConstraint('user_id', 'group_id'),)


class Teaching(Identity, Base):
    __tablename__ = 'teacher_assignments'
    teacher_id: Mapped[str] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'))
    group_id: Mapped[str] = mapped_column(ForeignKey('groups.id'))
    subject_id: Mapped[str] = mapped_column(ForeignKey('subjects.id'))
    __table_args__ = (UniqueConstraint('teacher_id', 'group_id', 'subject_id'),)


class Session(Identity, Base):
    __tablename__ = 'sessions'
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    csrf_token: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[object] = mapped_column(UTCDateTime(), index=True)


class LoginAttempt(Identity, Base):
    __tablename__ = 'login_attempts'
    key_hash: Mapped[str] = mapped_column(String(64), index=True)


class Conversation(Identity, Base):
    __tablename__ = 'conversations'
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    title: Mapped[str] = mapped_column(String(140), default='Nueva conversación')


class Message(Identity, Base):
    __tablename__ = 'messages'
    conversation_id: Mapped[str] = mapped_column(ForeignKey('conversations.id', ondelete='CASCADE'), index=True)
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    client_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    in_reply_to: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    __table_args__ = (UniqueConstraint('conversation_id', 'client_id'), CheckConstraint("role IN ('user','assistant')"))


class Memory(Identity, Base):
    __tablename__ = 'memories'
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    content: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(30), default='personal')
    event_at: Mapped[object | None] = mapped_column(UTCDateTime(), nullable=True, index=True)
    timezone: Mapped[str] = mapped_column(String(50), default='Europe/Madrid')
    source: Mapped[str] = mapped_column(String(100), default='Aportado voluntariamente por el usuario')


class MemorySummary(Identity, Base):
    __tablename__ = 'memory_summaries'
    conversation_id: Mapped[str] = mapped_column(ForeignKey('conversations.id', ondelete='CASCADE'), unique=True)
    content: Mapped[str] = mapped_column(Text)
    message_count: Mapped[int] = mapped_column(Integer)


class CalendarEvent(Identity, Base):
    __tablename__ = 'calendar_events'
    center_id: Mapped[str] = mapped_column(ForeignKey('centers.id'), index=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'))
    group_id: Mapped[str | None] = mapped_column(ForeignKey('groups.id'), nullable=True, index=True)
    subject_id: Mapped[str | None] = mapped_column(ForeignKey('subjects.id'), nullable=True)
    classroom_id: Mapped[str | None] = mapped_column(ForeignKey('classrooms.id'), nullable=True)
    title: Mapped[str] = mapped_column(String(180))
    description: Mapped[str] = mapped_column(Text, default='')
    kind: Mapped[str] = mapped_column(String(20), default='event')
    visibility: Mapped[str] = mapped_column(String(20), default='personal')
    starts_at: Mapped[object] = mapped_column(UTCDateTime(), index=True)
    ends_at: Mapped[object] = mapped_column(UTCDateTime())
    timezone: Mapped[str] = mapped_column(String(50), default='Europe/Madrid')
    status: Mapped[str] = mapped_column(String(20), default='published')
    source: Mapped[str] = mapped_column(String(100), default='Confirmado por docente')
    version: Mapped[int] = mapped_column(Integer, default=1)
    __table_args__ = (CheckConstraint('ends_at > starts_at'), CheckConstraint("visibility IN ('personal','group','center')"), CheckConstraint("status IN ('published','cancelled')"))


class Exam(Identity, Base):
    __tablename__ = 'exams'
    event_id: Mapped[str] = mapped_column(ForeignKey('calendar_events.id', ondelete='CASCADE'), unique=True)
    syllabus: Mapped[str] = mapped_column(Text, default='')


class Assignment(Identity, Base):
    __tablename__ = 'assignments'
    center_id: Mapped[str] = mapped_column(ForeignKey('centers.id'))
    group_id: Mapped[str] = mapped_column(ForeignKey('groups.id'), index=True)
    subject_id: Mapped[str] = mapped_column(ForeignKey('subjects.id'))
    creator_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    title: Mapped[str] = mapped_column(String(180))
    description: Mapped[str] = mapped_column(Text, default='')
    due_at: Mapped[object] = mapped_column(UTCDateTime(), index=True)
    material_ids: Mapped[list] = mapped_column(JSON, default=list)


class Submission(Identity, Base):
    __tablename__ = 'submissions'
    assignment_id: Mapped[str] = mapped_column(ForeignKey('assignments.id', ondelete='CASCADE'))
    student_id: Mapped[str] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'))
    content: Mapped[str] = mapped_column(Text, default='')
    status: Mapped[str] = mapped_column(String(20), default='submitted')
    __table_args__ = (UniqueConstraint('assignment_id', 'student_id'), CheckConstraint("status IN ('submitted','completed')"))


class Schedule(Identity, Base):
    __tablename__ = 'schedules'
    center_id: Mapped[str] = mapped_column(ForeignKey('centers.id'))
    group_id: Mapped[str] = mapped_column(ForeignKey('groups.id'), index=True)
    subject_id: Mapped[str] = mapped_column(ForeignKey('subjects.id'))
    teacher_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    classroom_id: Mapped[str | None] = mapped_column(ForeignKey('classrooms.id'), nullable=True)
    weekday: Mapped[int] = mapped_column(Integer)
    starts: Mapped[str] = mapped_column(String(5))
    ends: Mapped[str] = mapped_column(String(5))
    source: Mapped[str] = mapped_column(String(100), default='Horario confirmado')
    __table_args__ = (CheckConstraint('weekday >= 0 AND weekday <= 4'), CheckConstraint('ends > starts'))


class Document(Identity, Base):
    __tablename__ = 'documents'
    center_id: Mapped[str] = mapped_column(ForeignKey('centers.id'))
    owner_id: Mapped[str] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    group_id: Mapped[str | None] = mapped_column(ForeignKey('groups.id'), nullable=True)
    subject_id: Mapped[str | None] = mapped_column(ForeignKey('subjects.id'), nullable=True)
    title: Mapped[str] = mapped_column(String(180))
    filename: Mapped[str] = mapped_column(String(200))
    storage_key: Mapped[str] = mapped_column(String(100), unique=True)
    checksum: Mapped[str] = mapped_column(String(64))
    access: Mapped[str] = mapped_column(String(20), default='personal')
    source: Mapped[str] = mapped_column(String(180), default='Subida manual')
    status: Mapped[str] = mapped_column(String(20), default='provisional')
    version: Mapped[int] = mapped_column(Integer, default=1)
    size: Mapped[int] = mapped_column(Integer)
    __table_args__ = (CheckConstraint("access IN ('personal','group','center','public')"), CheckConstraint("status IN ('provisional','validated','official')"))


class DocumentChunk(Identity, Base):
    __tablename__ = 'document_chunks'
    document_id: Mapped[str] = mapped_column(ForeignKey('documents.id', ondelete='CASCADE'), index=True)
    ordinal: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    location: Mapped[str] = mapped_column(String(100), default='')
    __table_args__ = (UniqueConstraint('document_id', 'ordinal'),)


class Notification(Identity, Base):
    __tablename__ = 'notifications'
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    title: Mapped[str] = mapped_column(String(180))
    content: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(30))
    read: Mapped[bool] = mapped_column(Boolean, default=False)
    dedup_key: Mapped[str | None] = mapped_column(String(200), unique=True, nullable=True)


class BathroomPass(Identity, Base):
    __tablename__ = 'bathroom_passes'
    center_id: Mapped[str] = mapped_column(ForeignKey('centers.id'))
    student_id: Mapped[str] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'))
    group_id: Mapped[str] = mapped_column(ForeignKey('groups.id'), index=True)
    recorded_by: Mapped[str] = mapped_column(ForeignKey('users.id'))
    left_at: Mapped[object] = mapped_column(UTCDateTime(), default=utcnow)
    returned_at: Mapped[object | None] = mapped_column(UTCDateTime(), nullable=True)
    correction_reason: Mapped[str] = mapped_column(String(300), default='')
    __table_args__ = (Index('uq_active_bathroom_student', 'student_id', unique=True,
                           sqlite_where=text('returned_at IS NULL'), postgresql_where=text('returned_at IS NULL')),)


class ActionRequest(Identity, Base):
    __tablename__ = 'action_requests'
    center_id: Mapped[str] = mapped_column(ForeignKey('centers.id'))
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    tool: Mapped[str] = mapped_column(String(80))
    arguments: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(20), default='pending')
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    expires_at: Mapped[object] = mapped_column(UTCDateTime())
    __table_args__ = (CheckConstraint("status IN ('pending','executing','approved','rejected','expired')"),)


class Approval(Identity, Base):
    __tablename__ = 'approvals'
    action_id: Mapped[str] = mapped_column(ForeignKey('action_requests.id', ondelete='CASCADE'), unique=True)
    approver_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    decision: Mapped[str] = mapped_column(String(20))


class AuditLog(Identity, Base):
    __tablename__ = 'audit_logs'
    center_id: Mapped[str] = mapped_column(ForeignKey('centers.id'))
    actor_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    operation: Mapped[str] = mapped_column(String(80))
    object_type: Mapped[str] = mapped_column(String(40))
    object_id: Mapped[str] = mapped_column(String(36))
    details: Mapped[dict] = mapped_column(JSON, default=dict)


class ReviewReport(Identity, Base):
    __tablename__ = 'review_reports'
    center_id: Mapped[str] = mapped_column(ForeignKey('centers.id'))
    findings: Mapped[list] = mapped_column(JSON, default=list)
    trigger: Mapped[str] = mapped_column(String(20), default='manual')
    review_day: Mapped[str | None] = mapped_column(String(10), nullable=True)
    __table_args__ = (UniqueConstraint('center_id', 'review_day'),)

# Register additive 0.2 tables for metadata/migrations; no change to the frozen 0001.
from .knowledge_models import (AccountSetup,LearnerProfile,KnowledgeSource,AcademicTeacher,LearnerSubject,
    PersonalScheduleSlot,CourseUnit,EvaluationCriterion,AssessmentPolicy,LearningProgress,
    StudySession,StudyPlan,PersonalTask,IntegrationConnection,OAuthAttempt)
from .agent_models import (AgentRun,AgentStep,CenterModule,MemoryAnnotation,SemanticVector,MemoryRelation,
    ScheduledJob,JobExecution,GradeScenario,MaterialDraft,IntegrationSync)
from .atlas_models import CoreState,CoreRevision,InstitutionalSource,ProviderPolicy,RemoteInvitation
from .guest_models import GuestSession,GuestRate
from .teacher_models import TeacherDemoSession
from . import class_models  # Register native classes with the shared SQLAlchemy metadata.

from . import nebula_models  # Native education settings and demonstration structures.
