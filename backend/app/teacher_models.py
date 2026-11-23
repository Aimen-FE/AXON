"""A temporary teacher and its isolated fictitious institutional namespace."""
from sqlalchemy import ForeignKey,Integer,Boolean
from sqlalchemy.orm import Mapped,mapped_column
from .db import Base,Identity,UTCDateTime
class TeacherDemoSession(Identity,Base):
    __tablename__='teacher_demo_sessions'
    user_id:Mapped[str]=mapped_column(ForeignKey('users.id',ondelete='CASCADE'),unique=True,index=True)
    center_id:Mapped[str]=mapped_column(ForeignKey('centers.id'),unique=True,index=True)
    expires_at:Mapped[object]=mapped_column(UTCDateTime(),index=True)
    last_seen_at:Mapped[object]=mapped_column(UTCDateTime())
    request_count:Mapped[int]=mapped_column(Integer,default=0)
    revoked:Mapped[bool]=mapped_column(Boolean,default=False)
