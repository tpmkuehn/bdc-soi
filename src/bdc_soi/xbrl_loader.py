"""Arelle model loading with a project-local taxonomy cache (SPEC 11, 22.3).

Taxonomy files Arelle downloads (us-gaap, dei, xbrl core schemas) are stored under
``<cache>/arelle`` so that a rerun can be fully offline.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_CNTLR_LOCK = threading.Lock()
_CNTLR: Any = None


class XbrlLoadError(RuntimeError):
    pass


@dataclass
class LoadedModel:
    model: Any  # arelle ModelXbrl
    path: Path
    document_type: str  # instance | inline_xbrl | other
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    extension_namespaces: list[str] = field(default_factory=list)

    def close(self) -> None:
        try:
            self.model.close()
        except Exception as exc:  # pragma: no cover - defensive
            log.debug("model close failed: %s", exc)


def get_controller(cache_dir: Path, offline: bool = False) -> Any:
    """Return a process-wide Arelle controller with the project cache directory."""
    global _CNTLR
    from arelle import Cntlr

    with _CNTLR_LOCK:
        if _CNTLR is None:
            _CNTLR = Cntlr.Cntlr(logFileName="logToBuffer")
        arelle_cache = Path(cache_dir) / "arelle"
        arelle_cache.mkdir(parents=True, exist_ok=True)
        _CNTLR.webCache.cacheDir = str(arelle_cache)
        _CNTLR.webCache.workOffline = bool(offline)
        return _CNTLR


_STANDARD_NS_PREFIXES = (
    "http://www.xbrl.org/",
    "http://xbrl.org/",
    "http://fasb.org/",
    "http://xbrl.sec.gov/",
    "http://www.w3.org/",
    "http://xbrl.fasb.org/",
    "http://xbrl.ifrs.org/",
)


def load_model(path: Path, cache_dir: Path, offline: bool = False) -> LoadedModel:
    from arelle.ModelDocument import Type as DocType

    cntlr = get_controller(cache_dir, offline)
    cntlr.logger.messages.clear() if hasattr(cntlr.logger, "messages") else None
    model = cntlr.modelManager.load(str(path))
    if model is None or model.modelDocument is None:
        raise XbrlLoadError(f"Arelle could not load {path}")
    doc_type = model.modelDocument.type
    if doc_type == DocType.INSTANCE:
        kind = "instance"
    elif doc_type in (DocType.INLINEXBRL, getattr(DocType, "INLINEXBRLDOCUMENTSET", -1)):
        kind = "inline_xbrl"
    else:
        kind = "other"
    errors = [str(e) for e in model.errors]
    ext_ns = sorted(
        {
            d.targetNamespace
            for d in model.urlDocs.values()
            if d.targetNamespace and not d.targetNamespace.startswith(_STANDARD_NS_PREFIXES)
        }
    )
    if kind == "other":
        model.close()
        raise XbrlLoadError(f"{path} is not an XBRL instance or Inline XBRL document (type={doc_type})")
    if not model.facts and errors:
        model.close()
        raise XbrlLoadError(f"Arelle loaded no facts from {path}; errors: {errors[:5]}")
    return LoadedModel(model=model, path=Path(path), document_type=kind, errors=errors, extension_namespaces=ext_ns)
