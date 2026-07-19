"""Series pack: build ZIP and import into bot (+ optional frontend)."""

from __future__ import annotations

__version__ = "1.0.0"

from .service import build_pack_zip, import_pack_zip

__all__ = ["__version__", "build_pack_zip", "import_pack_zip"]
