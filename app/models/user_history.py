from sqlalchemy import Column, Integer, String, Numeric, DateTime, CheckConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from app.core.database import Base
from app.models.enums import tipe_tempat_enum
 
 
class UserHistory(Base):
    __tablename__ = "user_history"
 
    id           = Column(Integer, primary_key=True, autoincrement=True)
    user_id      = Column(UUID(as_uuid=True), nullable=False, index=True)
    tipe_tempat  = Column(tipe_tempat_enum, nullable=False)
    tempat_id    = Column(Integer, nullable=False)
    tempat_kode  = Column(String(20), nullable=False)
    aksi         = Column(String(30), nullable=False)
    nilai_rating = Column(Numeric(2, 1))
    durasi_detik = Column(Integer)
    created_at   = Column(DateTime(timezone=True), server_default=func.now())
 
    __table_args__ = (
        CheckConstraint("aksi IN ('klik','kunjungi','simpan','rating','share')",
                        name="ck_user_history_aksi"),
        CheckConstraint("nilai_rating BETWEEN 1.0 AND 5.0",
                        name="ck_user_history_rating"),
    )
 
    def __repr__(self):
        return f"<UserHistory user={self.user_id} aksi={self.aksi} tempat={self.tempat_kode}>"
