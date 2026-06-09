from __future__ import annotations

import hashlib
import os
from pathlib import Path


_DEFAULT_RAW_PDF_STORE_DIR = Path("logs") / "raw_pdfs"


def persist_raw_pdf_bytes(
    pdf_bytes: bytes,
    pdf_sha256: str,
    *,
    storage_dir: str | Path | None = None,
) -> str:
    """Persist raw PDF bytes in a sha-addressed filesystem store."""
    if hashlib.sha256(pdf_bytes).hexdigest() != pdf_sha256:
        raise ValueError("pdf_sha256 does not match pdf_bytes")
    root = _raw_pdf_store_root(storage_dir)
    target = root / pdf_sha256[:2] / f"{pdf_sha256}.pdf"
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        return target.resolve().as_uri()

    tmp = target.with_suffix(".pdf.tmp")
    tmp.write_bytes(pdf_bytes)
    tmp.replace(target)
    return target.resolve().as_uri()


def _raw_pdf_store_root(storage_dir: str | Path | None) -> Path:
    if storage_dir is not None:
        return Path(storage_dir)
    env_value = os.environ.get("MIROFLOW_RAW_PDF_STORE_DIR")
    if env_value:
        return Path(env_value)
    return _DEFAULT_RAW_PDF_STORE_DIR
