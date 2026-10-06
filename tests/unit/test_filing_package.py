from pathlib import Path

from bdc_soi.filing_package import choose_instance, classify_package_file, detect_xml_root, is_inline_xbrl_document, load_cached_package
from bdc_soi.models import PackageFile
from tests.conftest import SYN, SYN_ACCESSION, SYN_CIK, stage_synthetic_package


def test_classify_package_files():
    assert classify_package_file("abc-20250630.htm", "abc-20250630.htm") == "primary"
    assert classify_package_file("abc-20250630_htm.xml", None) == "xml"
    assert classify_package_file("abc-20250630_pre.xml", None) == "linkbase"
    assert classify_package_file("abc.xsd", None) == "schema"
    assert classify_package_file("R12.htm", None) is None
    assert classify_package_file("logo.jpg", None) is None
    assert classify_package_file("FilingSummary.xml", None) == "summary"


def test_instance_detection_by_root_not_filename(tmp_path: Path):
    inst = SYN / "package" / "syn-20250630_htm.xml"
    tag, _ = detect_xml_root(inst)
    assert tag == "{http://www.xbrl.org/2003/instance}xbrl"
    lab = SYN / "package" / "syn-20250630_lab.xml"
    assert detect_xml_root(lab)[0] == "{http://www.xbrl.org/2003/linkbase}linkbase"
    # A misleadingly named file is not an instance.
    fake = tmp_path / "fake_htm.xml"
    fake.write_text('<?xml version="1.0"?><root/>')
    files = [PackageFile(name="fake_htm.xml", url="u", local_path=str(fake), size=1, sha256="x", role="xml")]
    assert choose_instance(files, None).kind == "none"
    real = [PackageFile(name="syn-20250630_htm.xml", url="u", local_path=str(inst), size=1, sha256="x", role="xml"), PackageFile(name="aaa.xml", url="u", local_path=str(lab), size=1, sha256="x", role="xml")]
    choice = choose_instance(real, None)
    assert choice.kind == "extracted_instance" and choice.path.name == "syn-20250630_htm.xml" and "preferred_htm_xml" in choice.reason


def test_inline_fallback(tmp_path: Path):
    ix = tmp_path / "doc.htm"
    ix.write_text('<html xmlns:ix="http://www.xbrl.org/2013/inlineXBRL"><body><ix:header></ix:header><ix:nonFraction name="a">1</ix:nonFraction></body></html>')
    assert is_inline_xbrl_document(ix)
    files = [PackageFile(name="doc.htm", url="u", local_path=str(ix), size=1, sha256="x", role="primary")]
    choice = choose_instance(files, "doc.htm")
    assert choice.kind == "inline_xbrl"


def test_cached_package_roundtrip(tmp_path: Path):
    pkg = stage_synthetic_package(tmp_path)
    assert (pkg.directory / "package_manifest.json").exists()
    loaded = load_cached_package(tmp_path, SYN_CIK, SYN_ACCESSION)
    assert loaded is not None and loaded.instance.kind == "extracted_instance"
    assert loaded.checksums() == pkg.checksums() and all(len(v) == 64 for v in loaded.checksums().values())
