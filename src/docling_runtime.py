"""Optional Docling runtime for high-fidelity PDF/document extraction.

Docling (MIT, IBM) converts PDFs — including SCANNED / image-only PDFs via OCR —
as well as images and Office docs into clean Markdown that preserves layout,
reading order, and tables. This is the "best for all PDF types" scanner wired
into Pi's ingestion.

Optional dependency: when Docling is missing or a conversion fails, callers fall
back to pypdf (text-layer only), so the core never hard-depends on it. Mirrors
the optional-dependency pattern in src/markitdown_runtime.py.

The DocumentConverter loads ML models (layout, tables, OCR) on first use, so it
is created once and cached as a module-level singleton and reused across calls.
"""

import logging
import os

logger = logging.getLogger(__name__)

# File types Docling can scan (PDFs + common image formats for pure-image docs).
DOCLING_EXTS = frozenset(
    {".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}
)

# Set PAIOS_PDF_ENGINE=pypdf to skip Docling and use the fast text-layer path.
_ENGINE = os.getenv("PAIOS_PDF_ENGINE", "docling").strip().lower()

_converter = None  # cached DocumentConverter (loads models once)


def docling_enabled() -> bool:
    return _ENGINE != "pypdf"


def is_docling_format(path: str) -> bool:
    if not isinstance(path, str):
        return False
    return os.path.splitext(path)[1].lower() in DOCLING_EXTS


def _get_converter():
    """Return a cached Docling DocumentConverter (raises if Docling absent)."""
    global _converter
    if _converter is None:
        from docling.document_converter import DocumentConverter  # optional dep
        _converter = DocumentConverter()
    return _converter


def convert_to_markdown(path: str) -> str | None:
    """Scan a PDF/image/doc to Markdown via Docling (OCR-capable).

    Returns the extracted Markdown, or ``None`` if Docling is disabled,
    unavailable, or the conversion fails — callers degrade gracefully.
    """
    if not docling_enabled():
        return None
    try:
        conv = _get_converter()
    except ImportError:
        logger.warning("docling not installed; cannot scan %s", path)
        return None
    except Exception as e:
        logger.warning("docling converter init failed: %s", e)
        return None
    try:
        result = conv.convert(path)
        md = result.document.export_to_markdown()
        if md and md.strip():
            logger.info("docling scanned %s (%d chars)", os.path.basename(path), len(md))
            return md
        return None
    except Exception as e:
        logger.warning("docling failed to convert %s: %s", path, e)
        return None
