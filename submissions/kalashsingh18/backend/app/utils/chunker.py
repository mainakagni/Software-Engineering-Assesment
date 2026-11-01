# Compatibility shim — canonical implementation lives in app.rag.chunker
from app.rag.chunker import (  # noqa: F401
    extract_text_from_pdf,
    extract_text_from_plain,
    chunk_text,
)
