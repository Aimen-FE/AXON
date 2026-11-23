"""Additive 0.3 records. Private execution history never belongs to the admin audit."""
from sqlalchemy import String, Text, Integer, Boolean, Float, JSON, ForeignKey, UniqueConstraint, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base, Identity, UTCDateTime


class AgentRun(Identity, Base):
    __tablename__ = 'agent_runs'
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    center_id: Mapped[str] = mapped_column(ForeignKey('centers.id'))
    conversation_id: Mapped[str] = mapped_column(ForeignKey('conversations.id', ondelete='CASCADE'))
    message_id: Mapped[str] = mapped_column(ForeignKey('messages.id', ondelete='CASCADE'), unique=True)
    status: Mapped[str] = mapped_column(String(30), default='planned')
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    max_steps: Mapped[int] = mapped_column(Integer, default=8)
    deadline_at: Mapped[object] = mapped_column(UTCDateTime())
    planner: Mapped[str] = mapped_column(String(30), default='structured')
    __table_args__ = (CheckConstraint('max_steps>=1 AND max_steps<=8'),)


class AgentStep(Identity, Base):
    __tablename__ = 'agent_steps'
    run_id: Mapped[str] = mapped_column(ForeignKey('agent_runs.id', ondelete='CASCADE'), index=True)
    position: Mapped[int] = mapped_column(Integer)
    tool: Mapped[str] = mapped_column(String(80))
    label: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(30), default='planned')
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    dependencies: Mapped[list] = mapped_column(JSON, default=list)
    summary: Mapped[str] = mapped_column(String(500), default='')
    error_code: Mapped[str] = mapped_column(String(60), default='')
    action_id: Mapped[str | None] = mapped_column(ForeignKey('action_requests.id', ondelete='SET NULL'), nullable=True)
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    __table_args__ = (UniqueConstraint('run_id', 'position'),)


class CenterModule(Identity, Base):
    __tablename__ = 'center_modules'
    center_id: Mapped[str] = mapped_column(ForeignKey('centers.id', ondelete='CASCADE'))
    key: Mapped[str] = mapped_column(String(50))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    __table_args__ = (UniqueConstraint('center_id', 'key'),)


class MemoryAnnotation(Identity, Base):
    __tablename__ = 'memory_annotations'
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    memory_id: Mapped[str] = mapped_column(ForeignKey('memories.id', ondelete='CASCADE'), unique=True)
    source_message_id: Mapped[str | None] = mapped_column(ForeignKey('messages.id', ondelete='SET NULL'), nullable=True)
    state: Mapped[str] = mapped_column(String(20), default='provisional')
    provenance: Mapped[str] = mapped_column(String(160), default='Aportado por la persona; sin validar')
    __table_args__ = (CheckConstraint("state IN ('confirmed','provisional')"),)


class SemanticVector(Identity, Base):
    __tablename__ = 'semantic_vectors'
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    entity: Mapped[str] = mapped_column(String(30))
    record_id: Mapped[str] = mapped_column(String(36))
    model: Mapped[str] = mapped_column(String(160))
    content_hash: Mapped[str] = mapped_column(String(64))
    vector: Mapped[list] = mapped_column(JSON)
    __table_args__ = (UniqueConstraint('user_id', 'entity', 'record_id', 'model'),)


class MemoryRelation(Identity, Base):
    __tablename__ = 'memory_relations'
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    left_id: Mapped[str] = mapped_column(ForeignKey('memories.id', ondelete='CASCADE'))
    right_id: Mapped[str] = mapped_column(ForeignKey('memories.id', ondelete='CASCADE'))
    kind: Mapped[str] = mapped_column(String(30))
    confidence: Mapped[float] = mapped_column(Float)
    provenance: Mapped[str] = mapped_column(String(180))
    __table_args__ = (UniqueConstraint('user_id', 'left_id', 'right_id'), CheckConstraint('left_id<>right_id'))


class ScheduledJob(Identity, Base):
    __tablename__ = 'scheduled_jobs'
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    center_id: Mapped[str] = mapped_column(ForeignKey('centers.id'))
    title: Mapped[str] = mapped_column(String(160))
    kind: Mapped[str] = mapped_column(String(40))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    cancelled: Mapped[bool] = mapped_column(Boolean, default=False)
    interval_hours: Mapped[int] = mapped_column(Integer, default=24)
    next_run_at: Mapped[object] = mapped_column(UTCDateTime())
    __table_args__ = (CheckConstraint('interval_hours>=1 AND interval_hours<=168'),)


class JobExecution(Identity, Base):
    __tablename__ = 'job_executions'
    job_id: Mapped[str] = mapped_column(ForeignKey('scheduled_jobs.id', ondelete='CASCADE'), index=True)
    scheduled_for: Mapped[object] = mapped_column(UTCDateTime())
    status: Mapped[str] = mapped_column(String(30), default='running')
    summary: Mapped[str] = mapped_column(String(500), default='')
    __table_args__ = (UniqueConstraint('job_id', 'scheduled_for'),)


class GradeScenario(Identity, Base):
    __tablename__ = 'grade_scenarios'
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    subject_id: Mapped[str] = mapped_column(ForeignKey('subjects.id'))
    policy_id: Mapped[str | None] = mapped_column(ForeignKey('assessment_policies.id', ondelete='SET NULL'), nullable=True)
    input: Mapped[dict] = mapped_column(JSON)
    result: Mapped[dict] = mapped_column(JSON)
    __table_args__ = ()


class MaterialDraft(Identity, Base):
    __tablename__ = 'material_drafts'
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    subject_id: Mapped[str] = mapped_column(ForeignKey('subjects.id'))
    title: Mapped[str] = mapped_column(String(180))
    kind: Mapped[str] = mapped_column(String(30))
    content: Mapped[str] = mapped_column(Text)
    sources: Mapped[list] = mapped_column(JSON, default=list)
    state: Mapped[str] = mapped_column(String(30), default='draft')
    version: Mapped[int] = mapped_column(Integer, default=1)
    document_id: Mapped[str | None] = mapped_column(ForeignKey('documents.id', ondelete='SET NULL'), nullable=True)
    __table_args__ = (CheckConstraint("state IN ('draft','reviewed','shared')"),)


class IntegrationSync(Identity, Base):
    __tablename__ = 'integration_syncs'
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    provider: Mapped[str] = mapped_column(String(40), default='classroom')
    mode: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(30))
    counts: Mapped[dict] = mapped_column(JSON, default=dict)
    error_code: Mapped[str] = mapped_column(String(80), default='')
