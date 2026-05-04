from typing import Any, Optional
from pydantic import BaseModel
 
 
class BaseResponse(BaseModel):
    """Semua endpoint wajib menggunakan wrapper ini."""
    success: bool = True
    message: str  = "OK"
    data: Any     = None
 
 
class PaginatedResponse(BaseResponse):
    """Digunakan untuk endpoint list yang support pagination."""
    total:       int = 0
    page:        int = 1
    limit:       int = 10
    total_pages: int = 0