import pytest
from app.services.sentiment_service import _preprocess

def test_preprocess_regional_slang():
    """Memastikan slang daerah terkonversi dengan benar (Indramayu/Cirebon/Majalengka)."""
    raw = "apik pisan arep maning sing ayu"
    # apik -> bagus, arep -> mau, maning -> lagi, sing -> yang, ayu -> cantik
    clean = _preprocess(raw)
    assert "bagus" in clean
    assert "mau" in clean
    assert "lagi" in clean
    assert "yang" in clean
    assert "cantik" in clean

def test_preprocess_noise():
    raw = "TEMPATNYA bagus BANGET!!! 123"
    expected = "tempatnya bagus banget"
    assert _preprocess(raw) == expected