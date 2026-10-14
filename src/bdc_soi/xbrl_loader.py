"""Arelle model loading with a project-local taxonomy cache (SPEC 11, 22.3).

Taxonomy files Arelle downloads (us-gaap, dei, xbrl core schemas) are stored under
``<cache>/arelle`` so that a rerun can be fully offline. Online, Arelle's web cache sends
the same resolved SEC user agent as the filing downloads; without a usable contact the
controller refuses to go online instead of falling back to Arelle's built-in default.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from bdc_soi.config import USER_AGENT_SETUP_MESSAGE, is_genuine_user_agent

log = logging.getLogger(__name__)

_CNTLR_LOCK = threading.Lock()
_CNTLR: Any = None


class XbrlLoadError(RuntimeError):
    pass


class TaxonomyUserAgentError(XbrlLoadError):
    """Online taxonomy retrieval was requested without a usable SEC contact."""


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


def get_controller(cache_dir: Path, offline: bool = False, user_agent: str | None = None) -> Any:
    """Return a process-wide Arelle controller with the project cache directory.

    ``user_agent`` is the resolved SEC user agent; it is applied to Arelle's web cache so
    SEC-hosted taxonomy downloads identify the same monitored contact as filing downloads.
    When not offline and no genuine user agent is available the call fails before Arelle
    can make a request.
    """
    global _CNTLR
    if not offline and not is_genuine_user_agent(user_agent):
        raise TaxonomyUserAgentError("Arelle taxonomy retrieval refused: " + USER_AGENT_SETUP_MESSAGE)
    from arelle import Cntlr

    with _CNTLR_LOCK:
        if _CNTLR is None:
            _CNTLR = Cntlr.Cntlr(logFileName="logToBuffer")
        arelle_cache = Path(cache_dir) / "arelle"
        arelle_cache.mkdir(parents=True, exist_ok=True)
        _CNTLR.webCache.cacheDir = str(arelle_cache)
        _CNTLR.webCache.workOffline = bool(offline)
        # Never leave a previous run's contact on the shared controller; Arelle's setter restores
        # its default for None, which is only reachable offline (no requests are made).
        _CNTLR.webCache.httpUserAgent = user_agent if is_genuine_user_agent(user_agent) else None
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


def load_model(path: Path, cache_dir: Path, offline: bool = False, user_agent: str | None = None) -> LoadedModel:
    from arelle.ModelDocument import Type as DocType

    cntlr = get_controller(cache_dir, offline, user_agent)
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
