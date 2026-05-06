"""Sentiment Analysis Service — Anggi (Indramayu + Cirebon).

Lazy-load IndoBERT dan baseline sklearn dari folder ml/sentiment/.
Server tidak crash jika model belum tersedia — endpoint mengembalikan HTTP 503.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.sentiment import (
    SentimentBatchRequest,
    SentimentRequest,
    SentimentResponse,
    SentimentSummaryResponse,
    SentimentSyncResponse,
)

logger = logging.getLogger(__name__)

# ── Paths ──────────────────────────────────────────────────────────────────
_BASE         = Path(__file__).resolve().parents[2]
MODEL_DIR     = _BASE / "ml" / "sentiment" / "model"
TOKENIZER_DIR = MODEL_DIR / "tokenizer"
BASELINE_DIR  = _BASE / "ml" / "sentiment" / "baseline"

# ── Label map (konsisten dengan Ikhsan) ───────────────────────────────────
LABEL_MAP: Dict[int, str] = {0: "negatif", 1: "positif"}

# ── Slang dict Indramayu + Cirebon ────────────────────────────────────────
SLANG_DICT: Dict[str, str] = {
    "gak": "tidak", "ga": "tidak", "tdk": "tidak", "ngga": "tidak",
    "gk": "tidak", "g": "tidak", "bgs": "bagus", "mantap": "bagus",
    "keren": "bagus", "jelek": "buruk", "ancur": "buruk", "parah": "buruk",
    "enak": "lezat", "yummy": "lezat", "murah": "terjangkau",
    "rame": "ramai", "bs": "bisa", "hrs": "harus", "sdh": "sudah",
    "blm": "belum", "udh": "sudah", "aja": "saja", "yg": "yang",
    "dgn": "dengan", "utk": "untuk", "krn": "karena",
    # Khas Indramayu / Cirebon
    "ewean": "tidak", "ora": "tidak", "sing": "yang",
    "maning": "lagi", "arep": "mau", "apik": "bagus", "ayu": "cantik",
}


def _preprocess(raw: str) -> str:
    if not isinstance(raw, str):
        return ""
    t = raw.lower()
    t = re.sub(r"http\S+|www\S+", "", t)
    t = re.sub(r"@\w+|#\w+", "", t)
    t = re.sub(r"[^\w\s]", " ", t)
    t = re.sub(r"\d+", "", t)
    words = [SLANG_DICT.get(w, w) for w in t.split()]
    words = [w for w in words if w]
    return re.sub(r"\s+", " ", " ".join(words)).strip()


# ── Lazy model cache ───────────────────────────────────────────────────────
_bert_model = None
_bert_tok   = None
_pkl_cache: Dict[str, object] = {}


def _load_bert():
    global _bert_model, _bert_tok
    if _bert_model is not None:
        return _bert_model, _bert_tok
    try:
        import torch
        from transformers import (AutoModelForSequenceClassification,
                                  AutoTokenizer)
        if not MODEL_DIR.exists():
            raise FileNotFoundError(f"Folder tidak ada: {MODEL_DIR}")
        tok_dir = TOKENIZER_DIR if TOKENIZER_DIR.exists() else MODEL_DIR
        _bert_tok   = AutoTokenizer.from_pretrained(str(tok_dir))
        _bert_model = AutoModelForSequenceClassification.from_pretrained(str(MODEL_DIR))
        _bert_model.eval()
        logger.info("IndoBERT loaded from %s", MODEL_DIR)
        return _bert_model, _bert_tok
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Model IndoBERT belum tersedia. Jalankan training di Colab. ({exc})",
        )


def _load_pkl(name: str):
    if name in _pkl_cache:
        return _pkl_cache[name]
    try:
        import joblib
        path = BASELINE_DIR / f"{name}.pkl"
        if not path.exists():
            raise FileNotFoundError(path)
        _pkl_cache[name] = joblib.load(str(path))
        return _pkl_cache[name]
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Model {name}.pkl belum tersedia. ({exc})",
        )


def _infer(model_name: str, raw: str) -> Tuple[str, float, str]:
    """Return (sentimen, confidence, teks_bersih)."""
    clean = _preprocess(raw)
    if model_name == "indobert":
        import torch
        m, tok = _load_bert()
        device = next(m.parameters()).device
        enc    = tok(clean, return_tensors="pt", truncation=True,
                     max_length=128, padding=True)
        enc    = {k: v.to(device) for k, v in enc.items()}
        with torch.no_grad():
            logits = m(**enc).logits
        probs    = torch.softmax(logits, dim=1)[0].cpu().tolist()
        lbl_id   = int(torch.argmax(logits).item())
    else:
        import numpy as np
        clf    = _load_pkl(model_name)
        proba  = clf.predict_proba([clean])[0]
        lbl_id = int(np.argmax(proba))
        probs  = list(proba)

    return LABEL_MAP[lbl_id], round(probs[lbl_id], 4), clean


# ── Service ────────────────────────────────────────────────────────────────

class SentimentService:
    """Async service untuk pipeline analisis sentimen."""

    async def predict_and_save(
        self,
        payload: SentimentRequest,
        db: AsyncSession,
    ) -> SentimentResponse:
        sentimen, confidence, clean = _infer(payload.model, payload.text)

        await db.execute(
            text("""
                INSERT INTO sentiment_results
                    (tipe_tempat, tempat_kode, ulasan_asli, ulasan_bersih,
                     sentimen, confidence, model_used, sumber_scraping, scraped_at)
                VALUES
                    (:tipe, :kode, :asli, :bersih,
                     :sentimen, :conf, :model, 'api', NOW())
                ON CONFLICT DO NOTHING
            """),
            {"tipe": payload.tipe_tempat, "kode": payload.tempat_kode,
             "asli": payload.text, "bersih": clean,
             "sentimen": sentimen, "conf": confidence, "model": payload.model},
        )
        await db.commit()

        return SentimentResponse(
            text=payload.text,
            sentimen=sentimen,
            confidence=confidence,
            model_used=payload.model,
            tipe_tempat=payload.tipe_tempat,
            tempat_kode=payload.tempat_kode,
        )

    async def predict_batch(
        self,
        items: Iterable[SentimentRequest] | SentimentBatchRequest,
        db: AsyncSession,
    ) -> List[SentimentResponse]:
        item_list: List[SentimentRequest] = (
            items.items if isinstance(items, SentimentBatchRequest) else list(items)
        )
        results: List[SentimentResponse] = []
        for payload in item_list:
            results.append(await self.predict_and_save(payload, db))
        return results

    async def get_summary(
        self,
        wilayah: str,
        tipe_tempat: str,
        db: AsyncSession,
    ) -> SentimentSummaryResponse:
        type_clause = ""
        params: dict = {"wilayah": wilayah}
        if tipe_tempat != "all":
            type_clause = "AND tempat.tipe_tempat = :tipe_tempat"
            params["tipe_tempat"] = tipe_tempat

        result = await db.execute(text(f"""
            SELECT
                COUNT(*) AS total_ulasan,
                COUNT(*) FILTER (WHERE sr.sentimen = 'positif') AS total_positif,
                COUNT(*) FILTER (WHERE sr.sentimen = 'negatif') AS total_negatif,
                COUNT(*) FILTER (WHERE sr.sentimen = 'netral')  AS total_netral
            FROM sentiment_results sr
            JOIN (
                SELECT kode, wilayah::text AS wilayah, 'wisata'    AS tipe_tempat FROM wisata
                UNION ALL
                SELECT kode, wilayah::text AS wilayah, 'kuliner'   AS tipe_tempat FROM kuliner
                UNION ALL
                SELECT kode, wilayah::text AS wilayah, 'nongkrong' AS tipe_tempat FROM nongkrong
            ) tempat ON tempat.kode = sr.tempat_kode
                     AND tempat.tipe_tempat = sr.tipe_tempat::text
            WHERE tempat.wilayah = :wilayah {type_clause}
        """), params)

        row           = result.fetchone()
        total_ulasan  = int(row.total_ulasan  or 0)
        total_positif = int(row.total_positif or 0)
        total_negatif = int(row.total_negatif or 0)
        total_netral  = int(row.total_netral  or 0)

        return SentimentSummaryResponse(
            wilayah=wilayah,
            tipe_tempat=tipe_tempat,
            total_ulasan=total_ulasan,
            total_positif=total_positif,
            total_negatif=total_negatif,
            total_netral=total_netral,
            persen_positif=round(total_positif / total_ulasan * 100, 2) if total_ulasan else 0.0,
            persen_negatif=round(total_negatif / total_ulasan * 100, 2) if total_ulasan else 0.0,
        )

    async def sync_sentimen(
        self,
        tipe_tempat: str,
        kode: str,
        db: AsyncSession,
    ) -> SentimentSyncResponse:
        valid = {"wisata", "kuliner", "nongkrong"}
        if tipe_tempat not in valid:
            raise HTTPException(status_code=400, detail=f"tipe_tempat tidak valid: {tipe_tempat}")

        agg = await db.execute(text("""
            SELECT
                COUNT(*) FILTER (WHERE sentimen = 'positif') AS positif,
                COUNT(*) FILTER (WHERE sentimen = 'negatif') AS negatif,
                COUNT(*)                                      AS total
            FROM sentiment_results
            WHERE tempat_kode = :kode AND tipe_tempat = :tipe
        """), {"kode": kode, "tipe": tipe_tempat})

        row     = agg.fetchone()
        total   = int(row.total   or 0)
        positif = int(row.positif or 0)
        negatif = int(row.negatif or 0)

        dominant = "positif" if positif >= negatif else "negatif"
        skor     = round(positif / total, 4) if total else 0.0

        await db.execute(text(f"""
            UPDATE {tipe_tempat}
            SET sentimen             = :sentimen,
                skor_sentimen        = :skor,
                total_ulasan_scraped = :total,
                total_positif        = :positif,
                total_negatif        = :negatif,
                updated_at           = NOW()
            WHERE kode = :kode
        """), {"sentimen": dominant, "skor": skor,
               "total": total, "positif": positif,
               "negatif": negatif, "kode": kode})
        await db.commit()

        return SentimentSyncResponse(
            kode=kode, sentimen=dominant, skor_sentimen=skor,
            total=total, positif=positif, negatif=negatif,
        )


__all__ = ["SentimentService"]
