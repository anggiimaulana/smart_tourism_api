import pytest
from unittest.mock import AsyncMock, MagicMock
from app.services.wisata_service import WisataService

@pytest.mark.asyncio
async def test_wisata_list_sorting_rating_desc():
    service = WisataService()
    db = AsyncMock()
    
    # Mocking db results
    mock_result = MagicMock()
    mock_result.scalar.return_value = 10
    mock_result.fetchall.return_value = []
    db.execute.side_effect = [mock_result, mock_result] # one for count, one for list
    
    await service.list(
        wilayah=None, kategori=None, sentimen=None, q=None, 
        sort_by="rating", order="desc", page=1, limit=10, db=db
    )
    
    # Verify the SQL contains "ORDER BY rating_google DESC"
    args, kwargs = db.execute.call_args
    sql = args[0].text
    assert "ORDER BY rating_google DESC" in sql

@pytest.mark.asyncio
async def test_wisata_list_sorting_sentimen_asc():
    service = WisataService()
    db = AsyncMock()
    
    mock_result = MagicMock()
    mock_result.scalar.return_value = 10
    mock_result.fetchall.return_value = []
    db.execute.side_effect = [mock_result, mock_result]
    
    await service.list(
        wilayah=None, kategori=None, sentimen=None, q=None, 
        sort_by="sentimen", order="asc", page=1, limit=10, db=db
    )
    
    args, kwargs = db.execute.call_args
    sql = args[0].text
    assert "ORDER BY skor_sentimen ASC" in sql

@pytest.mark.asyncio
async def test_wisata_list_filter_sentimen_positif():
    """Memastikan filter sentimen (positif/negatif) ditambahkan ke WHERE clause."""
    service = WisataService()
    db = AsyncMock()
    
    mock_result = MagicMock()
    mock_result.scalar.return_value = 5
    mock_result.fetchall.return_value = []
    db.execute.side_effect = [mock_result, mock_result]
    
    await service.list(
        wilayah=None, kategori=None, sentimen="positif", q=None, 
        sort_by=None, order=None, page=1, limit=10, db=db
    )
    
    # Cek query count
    args_count, _ = db.execute.call_args_list[0]
    sql_count = args_count[0].text
    assert "sentimen::text = :sentimen" in sql_count
    
    # Cek query list
    args_list, _ = db.execute.call_args_list[1]
    sql_list = args_list[0].text
    assert "sentimen::text = :sentimen" in sql_list
