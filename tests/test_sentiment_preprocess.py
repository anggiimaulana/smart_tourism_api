import pytest
from app.services.sentiment_service import _preprocess

def test_preprocess_basic():
    """Test cleaning characters, lowercase, and basic slang."""
    raw = "TEMPATNYA bagus BANGET!!! 123"
    expected = "tempatnya bagus banget"
    assert _preprocess(raw) == expected

def test_preprocess_slang_general():
    """Test common Indonesian slang replacement."""
    raw = "makanan enak bgt tapi ga murah"
    # bgt -> banget (not in dict yet?), ga -> tidak, enak -> lezat
    # Wait, check SLANG_DICT in sentiment_service.py
    # "ga": "tidak", "enak": "lezat", "murah": "terjangkau"
    # "bgt" is NOT in SLANG_DICT yet.
    clean = _preprocess(raw)
    assert "lezat" in clean
    assert "tidak" in clean
    assert "terjangkau" in clean

def test_preprocess_slang_regional():
    """Test regional slang (Indramayu/Cirebon/Majalengka)."""
    raw = "apik pisan arep maning sing ayu"
    # apik -> bagus, arep -> mau, maning -> lagi, sing -> yang, ayu -> cantik
    clean = _preprocess(raw)
    assert "bagus" in clean
    assert "mau" in clean
    assert "lagi" in clean
    assert "yang" in clean
    assert "cantik" in clean

def test_preprocess_noise_removal():
    """Test URL and mention removal."""
    raw = "Cek di http://google.com @user #pantai"
    assert _preprocess(raw) == "cek di"

def test_preprocess_empty():
    assert _preprocess("") == ""
    assert _preprocess(None) == ""
