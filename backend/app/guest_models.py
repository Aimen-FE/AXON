"""Short-lived public demonstration identities; no permanent registration."""
from sqlalchemy import String,Integer,ForeignKey,Boolean,Index
from sqlalchemy.orm import Mapped,mapped_column
from .db import Base,Identity,UTCDateTime
class GuestSession(Identity,Base):
    __tablename__='guest_sessions'
    user_id:Mapped[str]=mapped_column(ForeignKey('users.id',ondelete='CASCADE'),unique=True,index=True)
    ip_hash:Mapped[str]=mapped_column(String(64),index=True)
    expires_at:Mapped[object]=mapped_column(UTCDateTime(),index=True)
    request_count:Mapped[int]=mapped_column(Integer,default=0)
    last_seen_at:Mapped[object]=mapped_column(UTCDateTime())
    revoked:Mapped[bool]=mapped_column(Boolean,default=False)
class GuestRate(Identity,Base):
    __tablename__='guest_rates'
    __table_args__=(Index('ix_guest_rates_window','key_hash','created_at'),)
    key_hash:Mapped[str]=mapped_column(String(64),index=True)
