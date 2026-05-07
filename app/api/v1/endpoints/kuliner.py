from typing import Literal, Optional
 
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
 
from app.core.database import get_db
from app.core.security import require_admin
from app.schemas.base import BaseResponse
from app.schemas.kuliner import KulinerCreate, KulinerUpdate
from app.services.kuliner_service import KulinerService
 
router = APIRouter()
 
 
@router.get("/", response_model=BaseResponse, summary="Daftar kuliner (publik)")
async def list_kuliner(
    wilayah:   Optional[Literal["Indramayu","Cirebon","Majalengka","Kuningan"]] = Query(None),
    jenis:     Optional[str]   = Query(None),
    sentimen:  Optional[str]   = Query(None),
    halal:     Optional[bool]  = Query(None),
    q:         Optional[str]   = Query(None, description="Cari nama atau menu"),
    sort_by:   Optional[Literal["rating", "sentimen"]] = Query("rating"),
    order:     Optional[Literal["asc", "desc"]]        = Query("desc"),
    page:      int             = Query(1, ge=1),
    limit:     int             = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    """
    Filter: wilayah, jenis_tempat, sentimen, halal, q.
    Sorting: rating (default), sentimen. Order: desc (default), asc.
    """
    service = KulinerService()
    result  = await service.list(wilayah, jenis, sentimen, halal, q, sort_by, order, page, limit, db)
    return BaseResponse(data=result)
 
 
@router.get("/{kode}", response_model=BaseResponse, summary="Detail kuliner berdasarkan kode")
async def get_kuliner(kode: str, db: AsyncSession = Depends(get_db)):
    service = KulinerService()
    result  = await service.get_by_kode(kode, db)
    if not result:
        raise HTTPException(status_code=404, detail=f"Kuliner '{kode}' tidak ditemukan")
    return BaseResponse(data=result)
 
 
@router.post("/", response_model=BaseResponse, status_code=201,
             summary="[Admin] Tambah kuliner baru",
             dependencies=[Depends(require_admin)])
async def create_kuliner(payload: KulinerCreate, db: AsyncSession = Depends(get_db)):
    service = KulinerService()
    result  = await service.create(payload, db)
    return BaseResponse(message="Kuliner berhasil ditambahkan", data=result)
 
 
@router.patch("/{kode}", response_model=BaseResponse,
              summary="[Admin] Update kuliner",
              dependencies=[Depends(require_admin)])
async def update_kuliner(kode: str, payload: KulinerUpdate, db: AsyncSession = Depends(get_db)):
    service = KulinerService()
    result  = await service.update(kode, payload, db)
    if not result:
        raise HTTPException(status_code=404, detail=f"Kuliner '{kode}' tidak ditemukan")
    return BaseResponse(message="Kuliner berhasil diperbarui", data=result)
 
 
@router.delete("/{kode}", response_model=BaseResponse,
               summary="[Admin] Hapus kuliner",
               dependencies=[Depends(require_admin)])
async def delete_kuliner(kode: str, db: AsyncSession = Depends(get_db)):
    service = KulinerService()
    deleted = await service.delete(kode, db)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Kuliner '{kode}' tidak ditemukan")
    return BaseResponse(message=f"Kuliner '{kode}' berhasil dihapus")