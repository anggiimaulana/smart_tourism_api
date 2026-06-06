from pydantic import BaseModel, Field, field_validator
from typing import Optional

class ReviewCreate(BaseModel):
    # Front-End wajib mengirimkan UUID tempat wisata/kuliner/nongkrong
    tempat_id: str = Field(..., description="ID tempat dalam bentuk UUID string")
    
    # Rating wajib berupa angka bulat dari 1 sampai 5
    rating: int = Field(..., ge=1, le=5, description="Rating skala 1 sampai 5")
    
    # Komentar boleh diisi, boleh juga dikosongkan (None)
    comment: Optional[str] = Field(None, description="Teks ulasan/komentar pengunjung")

    # Validator tambahan untuk memastikan angka rating tidak ngaco
    @field_validator('rating')
    @classmethod
    def validate_rating(cls, v):
        if v < 1 or v > 5:
            raise ValueError('Rating harus berada di antara angka 1 sampai 5')
        return v