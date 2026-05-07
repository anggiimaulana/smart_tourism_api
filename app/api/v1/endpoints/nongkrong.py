from typing import Literal, Optional
 
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
 
from app.core.database import get_db
from app.core.security import require_admin
from app.schemas.base import BaseResponse
from app.schemas.nongkrong import NongkrongCreate, NongkrongUpdate
from app.services.nongkrong_service import NongkrongService
 
router = APIRouter()
 
 
@router.get("/", response_model=BaseResponse, summary="Daftar nongkrong (publik)")
async def list_nongkrong(
    wilayah:  Optional[Literal["Indramayu","Cirebon","Majalengka","Kuningan"]] = Query(None),
    sentimen: Optional[str]   = Query(None),
    q:        Optional[str]   = Query(None, description="Cari nama atau konsep"),
    sort_by:  Optional[Literal["rating", "sentimen"]] = Query("rating"),
    order:    Optional[Literal["asc", "desc"]]        = Query("desc"),
    page:     int             = Query(1, ge=1),
    limit:    int             = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    """
    Filter: wilayah, sentimen, q.
    Sorting: rating (default), sentimen. Order: desc (default), asc.
    """
    service = NongkrongService()
    result  = await service.list(wilayah, sentimen, q, sort_by, order, page, limit, db)
    return BaseResponse(data=result)
 
 
@router.get("/{kode}", response_model=BaseResponse, summary="Detail nongkrong berdasarkan kode")
async def get_nongkrong(kode: str, db: AsyncSession = Depends(get_db)):
    service = NongkrongService()
    result  = await service.get_by_kode(kode, db)
    if not result:
        raise HTTPException(status_code=404, detail=f"Nongkrong '{kode}' tidak ditemukan")
    return BaseResponse(data=result)
 
 
@router.post("/", response_model=BaseResponse, status_code=201,
             summary="[Admin] Tambah tempat nongkrong baru",
             dependencies=[Depends(require_admin)])
async def create_nongkrong(payload: NongkrongCreate, db: AsyncSession = Depends(get_db)):
    service = NongkrongService()
    result  = await service.create(payload, db)
    return BaseResponse(message="Nongkrong berhasil ditambahkan", data=result)
 
 
@router.patch("/{kode}", response_model=BaseResponse,
              summary="[Admin] Update nongkrong",
              dependencies=[Depends(require_admin)])
async def update_nongkrong(kode: str, payload: NongkrongUpdate, db: AsyncSession = Depends(get_db)):
    service = NongkrongService()
    result  = await service.update(kode, payload, db)
    if not result:
        raise HTTPException(status_code=404, detail=f"Nongkrong '{kode}' tidak ditemukan")
    return BaseResponse(message="Nongkrong berhasil diperbarui", data=result)
 
 
@router.delete("/{kode}", response_model=BaseResponse,
               summary="[Admin] Hapus nongkrong",
               dependencies=[Depends(require_admin)])
async def delete_nongkrong(kode: str, db: AsyncSession = Depends(get_db)):
    service = NongkrongService()
    deleted = await service.delete(kode, db)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Nongkrong '{kode}' tidak ditemukan")
    return BaseResponse(message=f"Nongkrong '{kode}' berhasil dihapus")