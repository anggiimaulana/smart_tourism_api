# app/api/v1/endpoints/wisata.py
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import require_admin
from app.schemas.base import BaseResponse
from app.schemas.wisata import WisataCreate, WisataUpdate
from app.services.wisata_service import WisataService

router = APIRouter()


@router.get(
    "/",
    response_model=BaseResponse,
    summary="Daftar semua wisata (publik)",
)
async def list_wisata(
    wilayah:  Optional[Literal["Indramayu","Cirebon","Majalengka","Kuningan"]] = Query(None),
    kategori: Optional[str]  = Query(None, description="Alam | Buatan | Budaya | Religi | ..."),
    sentimen: Optional[str]  = Query(None, description="positif | negatif | netral"),
    q:        Optional[str]  = Query(None, description="Pencarian nama wisata"),
    page:     int            = Query(1, ge=1),
    limit:    int            = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    """
    Filter tersedia: wilayah, kategori_utama, sentimen, pencarian nama.
    Urutan default: rating_google DESC, skor_sentimen DESC.
    """
    service = WisataService()
    result = await service.list(wilayah, kategori, sentimen, q, page, limit, db)
    return BaseResponse(data=result)


@router.get(
    "/{kode}",
    response_model=BaseResponse,
    summary="Detail wisata berdasarkan kode",
)
async def get_wisata(kode: str, db: AsyncSession = Depends(get_db)):
    """
    Contoh kode: WIS-IDM-001
    """
    service = WisataService()
    result = await service.get_by_kode(kode, db)
    if not result:
        raise HTTPException(status_code=404, detail="Wisata tidak ditemukan")
    return BaseResponse(data=result)


@router.post(
    "/",
    response_model=BaseResponse,
    status_code=201,
    summary="[Admin] Tambah wisata baru",
    dependencies=[Depends(require_admin)],
)
async def create_wisata(payload: WisataCreate, db: AsyncSession = Depends(get_db)):
    """
    Kode wisata digenerate otomatis: WIS-{WILAYAH}-{NOMOR}.
    Hanya admin yang bisa mengakses.
    """
    service = WisataService()
    result = await service.create(payload, db)
    return BaseResponse(data=result)


@router.patch(
    "/{kode}",
    response_model=BaseResponse,
    summary="[Admin] Update sebagian data wisata",
    dependencies=[Depends(require_admin)],
)
async def update_wisata(kode: str, payload: WisataUpdate, db: AsyncSession = Depends(get_db)):
    """
    Hanya field yang dikirim yang akan diupdate (PATCH semantics).
    """
    service = WisataService()
    result = await service.update(kode, payload, db)
    if not result:
        raise HTTPException(status_code=404, detail="Wisata tidak ditemukan")
    return BaseResponse(data=result)


@router.delete(
    "/{kode}",
    response_model=BaseResponse,
    summary="[Admin] Hapus wisata",
    dependencies=[Depends(require_admin)],
)
async def delete_wisata(kode: str, db: AsyncSession = Depends(get_db)):
    service = WisataService()
    deleted = await service.delete(kode, db)
    if not deleted:
        raise HTTPException(status_code=404, detail="Wisata tidak ditemukan")
    return BaseResponse(message="Wisata berhasil dihapus")
