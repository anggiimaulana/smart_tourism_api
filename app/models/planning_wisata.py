from sqlalchemy import Column, Integer, String, Text, Date, DateTime, ARRAY, CheckConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func
from app.core.database import Base
 
 
class PlanningWisata(Base):
    __tablename__ = "planning_wisata"
 
    id              = Column(Integer, primary_key=True, autoincrement=True)
    user_id         = Column(UUID(as_uuid=True), nullable=False, index=True)
    judul           = Column(String(255), nullable=False)
    wilayah         = Column(ARRAY(String))
    tanggal_mulai   = Column(Date)
    tanggal_selesai = Column(Date)
    jumlah_orang    = Column(Integer, default=1)
    budget_total    = Column(Integer)
    catatan         = Column(Text)
    items           = Column(JSONB, nullable=False, default=list)
    status          = Column(String(30), default="draft")
    created_at      = Column(DateTime(timezone=True), server_default=func.now())
    updated_at      = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
 
    __table_args__ = (
        CheckConstraint("status IN ('draft','finalized','selesai')",
                        name="ck_planning_status"),
    )
 
    def __repr__(self):
        return f"<PlanningWisata id={self.id} judul={self.judul}>"