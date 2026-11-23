"""Conocimiento académico privado: ninguna fila concede permisos institucionales."""
from sqlalchemy import String, Text, Integer, Boolean, ForeignKey, JSON, UniqueConstraint, CheckConstraint
from sqlalchemy.orm import Mapped,mapped_column
from .db import Base,UTCDateTime,Identity

class AccountSetup(Identity,Base):
    __tablename__='account_setups'
    user_id:Mapped[str]=mapped_column(ForeignKey('users.id',ondelete='CASCADE'),unique=True)
    token_hash:Mapped[str]=mapped_column(String(64),unique=True)
    expires_at:Mapped[object]=mapped_column(UTCDateTime())
    used:Mapped[bool]=mapped_column(Boolean,default=False)

class LearnerProfile(Identity,Base):
    __tablename__='learner_profiles'
    user_id:Mapped[str]=mapped_column(ForeignKey('users.id',ondelete='CASCADE'),unique=True)
    group_id:Mapped[str]=mapped_column(ForeignKey('groups.id'))
    year_id:Mapped[str]=mapped_column(ForeignKey('academic_years.id'))
    program:Mapped[str]=mapped_column(String(180))
    preferences:Mapped[dict]=mapped_column(JSON,default=dict)
    availability:Mapped[list]=mapped_column(JSON,default=list)

class KnowledgeSource(Identity,Base):
    __tablename__='knowledge_sources'
    owner_id:Mapped[str]=mapped_column(ForeignKey('users.id',ondelete='CASCADE'),index=True)
    document_id:Mapped[str|None]=mapped_column(ForeignKey('documents.id',ondelete='CASCADE'),nullable=True,index=True)
    subject_id:Mapped[str|None]=mapped_column(ForeignKey('subjects.id'),nullable=True)
    title:Mapped[str]=mapped_column(String(180))
    kind:Mapped[str]=mapped_column(String(30),default='document')
    academic_year:Mapped[str|None]=mapped_column(String(20),nullable=True)
    applicable_year:Mapped[str]=mapped_column(String(20))
    verification:Mapped[str]=mapped_column(String(30),default='pending')
    url:Mapped[str|None]=mapped_column(String(1500),nullable=True)
    checked_at:Mapped[object|None]=mapped_column(UTCDateTime(),nullable=True)
    source_location:Mapped[str]=mapped_column(String(180),default='')
    warnings:Mapped[list]=mapped_column(JSON,default=list)
    __table_args__=(CheckConstraint("verification IN ('pending','historical','teacher_confirmed','official_verified')"),)

class AcademicTeacher(Identity,Base):
    __tablename__='academic_teachers'
    owner_id:Mapped[str]=mapped_column(ForeignKey('users.id',ondelete='CASCADE'),index=True)
    source_id:Mapped[str]=mapped_column(ForeignKey('knowledge_sources.id',ondelete='CASCADE'))
    subject_id:Mapped[str]=mapped_column(ForeignKey('subjects.id'))
    display_name:Mapped[str]=mapped_column(String(120))
    contact:Mapped[str|None]=mapped_column(String(180),nullable=True)
    __table_args__=(UniqueConstraint('owner_id','source_id','subject_id','display_name'),)

class LearnerSubject(Identity,Base):
    __tablename__='learner_subjects'
    user_id:Mapped[str]=mapped_column(ForeignKey('users.id',ondelete='CASCADE'),index=True)
    subject_id:Mapped[str]=mapped_column(ForeignKey('subjects.id'))
    active:Mapped[bool]=mapped_column(Boolean,default=True)
    source_id:Mapped[str|None]=mapped_column(ForeignKey('knowledge_sources.id',ondelete='SET NULL'),nullable=True)
    __table_args__=(UniqueConstraint('user_id','subject_id'),)

class PersonalScheduleSlot(Identity,Base):
    __tablename__='personal_schedule_slots'
    owner_id:Mapped[str]=mapped_column(ForeignKey('users.id',ondelete='CASCADE'),index=True)
    source_id:Mapped[str]=mapped_column(ForeignKey('knowledge_sources.id',ondelete='CASCADE'),index=True)
    group_id:Mapped[str]=mapped_column(ForeignKey('groups.id'))
    subject_id:Mapped[str|None]=mapped_column(ForeignKey('subjects.id'),nullable=True)
    weekday:Mapped[int]=mapped_column(Integer)
    starts:Mapped[str]=mapped_column(String(5))
    ends:Mapped[str]=mapped_column(String(5))
    raw_code:Mapped[str]=mapped_column(String(60),default='')
    teacher:Mapped[str]=mapped_column(String(120),default='')
    classroom:Mapped[str]=mapped_column(String(60),default='')
    is_break:Mapped[bool]=mapped_column(Boolean,default=False)
    overridden:Mapped[bool]=mapped_column(Boolean,default=False)
    __table_args__=(CheckConstraint('weekday>=0 AND weekday<=4'),CheckConstraint('ends>starts'),UniqueConstraint('source_id','weekday','starts','raw_code'))

class CourseUnit(Identity,Base):
    __tablename__='course_units'
    owner_id:Mapped[str]=mapped_column(ForeignKey('users.id',ondelete='CASCADE'),index=True)
    subject_id:Mapped[str]=mapped_column(ForeignKey('subjects.id'))
    source_id:Mapped[str]=mapped_column(ForeignKey('knowledge_sources.id',ondelete='CASCADE'),index=True)
    code:Mapped[str]=mapped_column(String(30))
    title:Mapped[str]=mapped_column(String(300))
    term:Mapped[int|None]=mapped_column(Integer,nullable=True)
    sessions:Mapped[int|None]=mapped_column(Integer,nullable=True)
    criteria:Mapped[list]=mapped_column(JSON,default=list)
    content:Mapped[str]=mapped_column(Text,default='')
    location:Mapped[str]=mapped_column(String(150),default='')
    __table_args__=(UniqueConstraint('source_id','code'),)

class EvaluationCriterion(Identity,Base):
    __tablename__='evaluation_criteria'
    owner_id:Mapped[str]=mapped_column(ForeignKey('users.id',ondelete='CASCADE'),index=True)
    subject_id:Mapped[str]=mapped_column(ForeignKey('subjects.id'))
    source_id:Mapped[str]=mapped_column(ForeignKey('knowledge_sources.id',ondelete='CASCADE'))
    code:Mapped[str]=mapped_column(String(30))
    competence:Mapped[str]=mapped_column(String(300),default='')
    content:Mapped[str]=mapped_column(Text,default='')
    instruments:Mapped[list]=mapped_column(JSON,default=list)
    __table_args__=(UniqueConstraint('source_id','code'),)

class AssessmentPolicy(Identity,Base):
    __tablename__='assessment_policies'
    owner_id:Mapped[str]=mapped_column(ForeignKey('users.id',ondelete='CASCADE'),index=True)
    subject_id:Mapped[str]=mapped_column(ForeignKey('subjects.id'))
    source_id:Mapped[str]=mapped_column(ForeignKey('knowledge_sources.id',ondelete='CASCADE'),unique=True)
    scheme:Mapped[str]=mapped_column(String(40))
    weights:Mapped[dict]=mapped_column(JSON,default=dict)
    final_weights:Mapped[list]=mapped_column(JSON,default=list)
    conditions:Mapped[dict]=mapped_column(JSON,default=dict)
    rules_text:Mapped[str]=mapped_column(Text,default='')

class LearningProgress(Identity,Base):
    __tablename__='learning_progress'
    user_id:Mapped[str]=mapped_column(ForeignKey('users.id',ondelete='CASCADE'),index=True)
    unit_id:Mapped[str]=mapped_column(ForeignKey('course_units.id',ondelete='CASCADE'))
    state:Mapped[str]=mapped_column(String(30),default='not_started')
    confidence:Mapped[int]=mapped_column(Integer,default=0)
    notes:Mapped[str]=mapped_column(Text,default='')
    __table_args__=(UniqueConstraint('user_id','unit_id'),CheckConstraint("state IN ('not_started','in_progress','review','mastered')"),CheckConstraint('confidence>=0 AND confidence<=5'))

class StudySession(Identity,Base):
    __tablename__='study_sessions'
    user_id:Mapped[str]=mapped_column(ForeignKey('users.id',ondelete='CASCADE'),index=True)
    subject_id:Mapped[str]=mapped_column(ForeignKey('subjects.id'))
    topic:Mapped[str]=mapped_column(String(200))
    mode:Mapped[str]=mapped_column(String(30),default='guided')
    level:Mapped[int]=mapped_column(Integer,default=1)
    exercises:Mapped[list]=mapped_column(JSON,default=list)
    attempts:Mapped[list]=mapped_column(JSON,default=list)
    source_id:Mapped[str|None]=mapped_column(ForeignKey('knowledge_sources.id',ondelete='SET NULL'),nullable=True)

class StudyPlan(Identity,Base):
    __tablename__='study_plans'
    user_id:Mapped[str]=mapped_column(ForeignKey('users.id',ondelete='CASCADE'),index=True)
    title:Mapped[str]=mapped_column(String(180))
    sessions:Mapped[list]=mapped_column(JSON,default=list)
    status:Mapped[str]=mapped_column(String(30),default='draft')
    event_ids:Mapped[list]=mapped_column(JSON,default=list)
    __table_args__=(CheckConstraint("status IN ('draft','confirmed','rejected')"),)

class PersonalTask(Identity,Base):
    __tablename__='personal_tasks'
    user_id:Mapped[str]=mapped_column(ForeignKey('users.id',ondelete='CASCADE'),index=True)
    subject_id:Mapped[str|None]=mapped_column(ForeignKey('subjects.id'),nullable=True)
    title:Mapped[str]=mapped_column(String(180))
    description:Mapped[str]=mapped_column(Text,default='')
    due_at:Mapped[object]=mapped_column(UTCDateTime())
    completed:Mapped[bool]=mapped_column(Boolean,default=False)
    source:Mapped[str]=mapped_column(String(180),default='Tarea personal')
    external_key:Mapped[str|None]=mapped_column(String(200),unique=True,nullable=True)

class IntegrationConnection(Identity,Base):
    __tablename__='integration_connections'
    user_id:Mapped[str]=mapped_column(ForeignKey('users.id',ondelete='CASCADE'),index=True)
    provider:Mapped[str]=mapped_column(String(40))
    mode:Mapped[str]=mapped_column(String(20),default='unconfigured')
    status:Mapped[str]=mapped_column(String(30),default='disconnected')
    encrypted_payload:Mapped[str]=mapped_column(Text,default='')
    expires_at:Mapped[object|None]=mapped_column(UTCDateTime(),nullable=True)
    last_sync:Mapped[object|None]=mapped_column(UTCDateTime(),nullable=True)
    last_error:Mapped[str]=mapped_column(String(200),default='')
    __table_args__=(UniqueConstraint('user_id','provider'),)

class OAuthAttempt(Identity,Base):
    __tablename__='oauth_attempts'
    user_id:Mapped[str]=mapped_column(ForeignKey('users.id',ondelete='CASCADE'))
    state_hash:Mapped[str]=mapped_column(String(64),unique=True)
    encrypted_verifier:Mapped[str]=mapped_column(Text)
    expires_at:Mapped[object]=mapped_column(UTCDateTime())
    used:Mapped[bool]=mapped_column(Boolean,default=False)
