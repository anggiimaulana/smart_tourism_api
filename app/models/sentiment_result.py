from sqlalchemy import Column, Integer, String, Text, Numeric, DateTime
from sqlalchemy.sql import func
from app.core.database import Base
from app.models.enums import model_sentimen_enum, sentimen_enum, tipe_tempat_enum
 
 
class SentimentResult(Base):
    __tablename__ = "sentiment_results"
 
    id              = Column(Integer, primary_key=True, autoincrement=True)
    tipe_tempat     = Column(tipe_tempat_enum, nullable=False)
    tempat_id       = Column(Integer)
    tempat_kode     = Column(String(20), nullable=False, index=True)
    ulasan_asli     = Column(Text, nullable=False)
    ulasan_bersih   = Column(Text)
    sentimen        = Column(sentimen_enum, nullable=False)
    confidence      = Column(Numeric(5, 4), nullable=False)
    model_used      = Column(model_sentimen_enum, nullable=False)
    sumber_scraping = Column(String(100))
    scraped_at      = Column(DateTime(timezone=True))
    created_at      = Column(DateTime(timezone=True), server_default=func.now())
 
    def __repr__(self):
        return f"<SentimentResult id={self.id} kode={self.tempat_kode} sentimen={self.sentimen}>"
