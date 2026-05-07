import pytest
from unittest.mock import AsyncMock, MagicMock
from app.services.sentiment_service import SentimentService

@pytest.mark.asyncio
async def test_get_summary_valid():
    """Test aggregation summary for a region."""
    service = SentimentService()
    db = AsyncMock()
    
    # Mock row result
    mock_row = MagicMock()
    mock_row.total_ulasan = 100
    mock_row.total_positif = 80
    mock_row.total_negatif = 15
    mock_row.total_netral = 5
    
    mock_result = MagicMock()
    mock_result.fetchone.return_value = mock_row
    db.execute.return_value = mock_result
    
    result = await service.get_summary("Indramayu", "wisata", db)
    
    assert result.wilayah == "Indramayu"
    assert result.total_ulasan == 100
    assert result.persen_positif == 80.0
    assert result.persen_negatif == 15.0

@pytest.mark.asyncio
async def test_sync_sentimen_updates_master():
    """Test sync logic updates master table with correct counts."""
    service = SentimentService()
    db = AsyncMock()
    
    # Mock aggregation: 50 reviews, 40 pos, 10 neg
    mock_row = MagicMock()
    mock_row.total = 50
    mock_row.positif = 40
    mock_row.negatif = 10
    
    mock_result = MagicMock()
    mock_result.fetchone.return_value = mock_row
    db.execute.return_value = mock_result
    
    result = await service.sync_sentimen("wisata", "WIS-IDM-001", db)
    
    assert result.kode == "WIS-IDM-001"
    assert result.sentimen == "positif"
    assert result.skor_sentimen == 0.8
    assert result.positif == 40
    
    # Ensure update query was called
    # We can check the SQL in call_args but simplified check is fine
    assert db.commit.called

@pytest.mark.asyncio
async def test_sync_all_calls_sync_sentimen():
    """Test sync_all iterates over distinct places."""
    service = SentimentService()
    db = AsyncMock()
    
    # Mock distinct places: 2 items
    mock_res_distinct = MagicMock()
    mock_res_distinct.fetchall.return_value = [("wisata", "W1"), ("kuliner", "K1")]
    
    # Mock sync_sentimen rows
    mock_row_sync = MagicMock()
    mock_row_sync.total = 5
    mock_row_sync.positif = 3
    mock_row_sync.negatif = 2
    
    mock_res_sync = MagicMock()
    mock_res_sync.fetchone.return_value = mock_row_sync
    
    # Each sync_sentimen call executes 2 statements (Select aggregation and Update)
    # 1 (distinct) + 2 places * 2 stmts = 5 results needed
    db.execute.side_effect = [
        mock_res_distinct, 
        mock_res_sync, MagicMock(), # Place 1 (Select, Update)
        mock_res_sync, MagicMock()  # Place 2 (Select, Update)
    ]
    
    result = await service.sync_all(db)
    
    assert result["total_synced"] == 2
    assert db.execute.call_count == 5
