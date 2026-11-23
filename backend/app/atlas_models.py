"""Additive ATLAS records. No personal history belongs in the shared core."""
from sqlalchemy import String,Text,Integer,Boolean,ForeignKey,JSON,UniqueConstraint
from sqlalchemy.orm import Mapped,mapped_column
from .db import Base,Identity,UTCDateTime

class CoreState(Identity,Base):
    __tablename__='core_states'
    center_id:Mapped[str]=mapped_column(ForeignKey('centers.id'),unique=True)
    version:Mapped[int]=mapped_column(Integer,default=1)
    payload:Mapped[dict]=mapped_column(JSON,default=dict)

class CoreRevision(Identity,Base):
    __tablename__='core_revisions'
    center_id:Mapped[str]=mapped_column(ForeignKey('centers.id'),index=True)
    version:Mapped[int]=mapped_column(Integer)
    payload:Mapped[dict]=mapped_column(JSON)
    actor_id:Mapped[str|None]=mapped_column(ForeignKey('users.id',ondelete='SET NULL'),nullable=True)
    reason:Mapped[str]=mapped_column(String(300))
    __table_args__=(UniqueConstraint('center_id','version'),)

class InstitutionalSource(Identity,Base):
    __tablename__='institutional_sources'
    center_id:Mapped[str]=mapped_column(ForeignKey('centers.id'),index=True)
    document_id:Mapped[str]=mapped_column(ForeignKey('documents.id',ondelete='CASCADE'),unique=True)
    source_url:Mapped[str]=mapped_column(String(1200))
    category:Mapped[str]=mapped_column(String(50))
    published_on:Mapped[str|None]=mapped_column(String(30),nullable=True)
    checked_on:Mapped[str]=mapped_column(String(30))
    academic_year:Mapped[str|None]=mapped_column(String(30),nullable=True)
    verification:Mapped[str]=mapped_column(String(30),default='verified_origin')
    applicability:Mapped[str]=mapped_column(String(30),default='unconfirmed')
    authority:Mapped[str]=mapped_column(String(40),default='school')
    notes:Mapped[str]=mapped_column(Text,default='')

class ProviderPolicy(Identity,Base):
    __tablename__='provider_policies'
    center_id:Mapped[str]=mapped_column(ForeignKey('centers.id'),unique=True)
    version:Mapped[int]=mapped_column(Integer,default=1)
    payload:Mapped[dict]=mapped_column(JSON,default=dict)

class RemoteInvitation(Identity,Base):
    __tablename__='remote_invitations'
    user_id:Mapped[str]=mapped_column(ForeignKey('users.id',ondelete='CASCADE'),unique=True)
    email:Mapped[str]=mapped_column(String(254),unique=True)
    token_hash:Mapped[str]=mapped_column(String(64),unique=True)
    expires_at:Mapped[object]=mapped_column(UTCDateTime())
    consumed:Mapped[bool]=mapped_column(Boolean,default=False)
    revoked:Mapped[bool]=mapped_column(Boolean,default=False)
