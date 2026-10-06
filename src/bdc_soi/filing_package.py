"""Accession package retrieval, checksums and instance detection (SPEC 10.2)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from lxml import etree

from bdc_soi.models import PackageFile
from bdc_soi.sec_client import (
    SecClient,
    accession_file_url,
    accession_index_url,
    accession_nodash,
    is_illustrative_accession,
    normalize_accession,
    normalize_cik,
)

XBRLI_NS = "http://www.xbrl.org/2003/instance"
IX_NS_RE = re.compile(r"http://www\.xbrl\.org/(2008|2013)/inlineXBRL")
_RENDERED_RE = re.compile(r"^R\d+\.htm$", re.IGNORECASE)
_SKIP_EXT = {".jpg", ".jpeg", ".gif", ".png", ".pdf", ".zip", ".txt", ".paper", ".js", ".css"}


class PackageError(RuntimeError):
    pass


@dataclass
class InstanceChoice:
    path: Path | None
    kind: str  # extracted_instance | inline_xbrl | none
    reason: str
    candidates: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class FilingPackage:
    cik: str
    accession_number: str
    directory: Path
    files: list[PackageFile]
    primary_document: str | None
    instance: InstanceChoice
    index_json: dict[str, Any]

    def file(self, name: str) -> PackageFile | None:
        return next((f for f in self.files if f.name == name), None)

    @property
    def primary_path(self) -> Path | None:
        f = self.file(self.primary_document) if self.primary_document else None
        return Path(f.local_path) if f else None

    def checksums(self) -> dict[str, str]:
        return {f.name: f.sha256 for f in sorted(self.files, key=lambda x: x.name)}

    def write_manifest(self) -> Path:
        manifest = {
            "cik": self.cik,
            "accession_number": self.accession_number,
            "primary_document": self.primary_document,
            "instance": {"path": str(self.instance.path.name) if self.instance.path else None, "kind": self.instance.kind, "reason": self.instance.reason},
            "files": [f.model_dump(mode="json") for f in sorted(self.files, key=lambda x: x.name)],
        }
        p = self.directory / "package_manifest.json"
        p.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
        return p


def classify_package_file(name: str, primary_document: str | None) -> str | None:
    """Return a file role, or None if the file should not be downloaded."""
    lower = name.lower()
    ext = Path(lower).suffix
    if name == "index.json" or lower == "package_manifest.json":
        return None
    if primary_document and name == primary_document:
        return "primary"
    if lower == "filingsummary.xml":
        return "summary"
    if lower == "metalinks.json":
        return "metadata"
    if ext == ".xsd":
        return "schema"
    if ext == ".xml":
        if re.search(r"_(pre|lab|cal|def)\.xml$", lower):
            return "linkbase"
        return "xml"
    if ext in {".htm", ".html", ".xhtml"}:
        if _RENDERED_RE.match(name):
            return None
        return "html"
    if ext in _SKIP_EXT:
        return None
    return None


def detect_xml_root(path: Path) -> tuple[str | None, set[str]]:
    """Return (root Clark tag, namespaces declared) using streaming parse of the first element."""
    try:
        for _event, elem in etree.iterparse(str(path), events=("start",), recover=True, huge_tree=True):
            tag = elem.tag if isinstance(elem.tag, str) else None
            nsmap = set(v for v in (elem.nsmap or {}).values() if v)
            return tag, nsmap
    except (etree.XMLSyntaxError, OSError):
        return None, set()
    return None, set()


def is_inline_xbrl_document(path: Path) -> bool:
    try:
        with path.open("rb") as fh:
            head = fh.read(200_000).decode("utf-8", errors="ignore")
    except OSError:
        return False
    return bool(IX_NS_RE.search(head)) and ("<ix:" in head or "ix:nonFraction" in head or "ix:header" in head)


def choose_instance(files: list[PackageFile], primary_document: str | None) -> InstanceChoice:
    """Prefer an XML whose root is xbrli:xbrl (prefer _htm.xml), else the inline primary document."""
    candidates: list[dict[str, Any]] = []
    instance_files: list[PackageFile] = []
    for f in sorted(files, key=lambda x: x.name):
        if f.role in {"xml", "schema", "linkbase", "summary"} or f.name.lower().endswith(".xml"):
            if f.role in {"schema", "linkbase", "summary"}:
                continue
            tag, _ns = detect_xml_root(Path(f.local_path))
            is_instance = tag == f"{{{XBRLI_NS}}}xbrl"
            candidates.append({"name": f.name, "root": tag, "is_instance": is_instance})
            if is_instance:
                instance_files.append(f)
    if instance_files:
        preferred = [f for f in instance_files if f.name.lower().endswith("_htm.xml")]
        chosen = preferred[0] if preferred else instance_files[0]
        reason = "root_is_xbrli_xbrl" + (";preferred_htm_xml" if preferred else "")
        if len(instance_files) > 1:
            reason += f";{len(instance_files)}_instances_sorted_by_name"
        return InstanceChoice(Path(chosen.local_path), "extracted_instance", reason, candidates)
    if primary_document:
        pf = next((f for f in files if f.name == primary_document), None)
        if pf and is_inline_xbrl_document(Path(pf.local_path)):
            candidates.append({"name": pf.name, "root": "inline", "is_instance": True})
            return InstanceChoice(Path(pf.local_path), "inline_xbrl", "no_extracted_instance;primary_document_is_inline_xbrl", candidates)
    return InstanceChoice(None, "none", "no_instance_or_inline_document_found", candidates)


def retrieve_package(client: SecClient, cik: str | int, accession: str, primary_document: str | None = None) -> FilingPackage:
    cik = normalize_cik(cik)
    accession = normalize_accession(accession)
    if is_illustrative_accession(accession):
        raise PackageError(f"accession {accession} is an illustrative placeholder and will not be fetched")
    directory = client.cache_dir / "sec" / "filings" / cik / accession_nodash(accession)
    index_url = accession_index_url(cik, accession, client.config.base_archive_url)
    index_data, _ = client.fetch_json(index_url, directory / "index.json")
    items = index_data.get("directory", {}).get("item", [])
    files: list[PackageFile] = []
    names = sorted(str(it.get("name")) for it in items if it.get("name"))
    sizes = {str(it.get("name")): it.get("size") for it in items}
    if primary_document is None:
        # Fall back to the largest top-level .htm that is not a rendered R file; recorded as a heuristic.
        htm = [n for n in names if n.lower().endswith(".htm") and not _RENDERED_RE.match(n)]
        primary_document = htm[0] if htm else None
    for name in names:
        role = classify_package_file(name, primary_document)
        if role is None:
            continue
        url = accession_file_url(cik, accession, name, client.config.base_archive_url)
        res = client.fetch_to_cache(url, directory / name)
        files.append(PackageFile(name=name, url=url, local_path=str(res.local_path), size=res.size, sha256=res.sha256, content_type=res.content_type, role=role, from_cache=res.from_cache))
    _ = sizes
    instance = choose_instance(files, primary_document)
    pkg = FilingPackage(cik, accession, directory, files, primary_document, instance, index_data)
    pkg.write_manifest()
    return pkg


def load_cached_package(cache_dir: Path, cik: str | int, accession: str) -> FilingPackage | None:
    """Rebuild a package from its cached manifest without any network access."""
    cik = normalize_cik(cik)
    accession = normalize_accession(accession)
    directory = Path(cache_dir) / "sec" / "filings" / cik / accession_nodash(accession)
    manifest = directory / "package_manifest.json"
    if not manifest.exists():
        return None
    data = json.loads(manifest.read_text(encoding="utf-8"))
    files = [PackageFile.model_validate({**f, "from_cache": True}) for f in data["files"]]
    for f in files:
        if not Path(f.local_path).exists():
            return None
    primary = data.get("primary_document")
    instance = choose_instance(files, primary)
    index_path = directory / "index.json"
    index_data = json.loads(index_path.read_text(encoding="utf-8")) if index_path.exists() else {}
    return FilingPackage(cik, accession, directory, files, primary, instance, index_data)
