"""api/services/knowledge/ingest.py::ingest_file — path restriction
(Security Item 3, F5). POST /api/knowledge/ingest is admin-key-gated but
previously passed a free-form file_path straight to ingest_file() with no
directory allowlist, permitting an admin-key holder to read/ingest arbitrary
files on the container filesystem rather than just approved knowledge-source
Markdown. Fixed by canonicalizing the path and rejecting anything that
resolves outside the knowledge/ base directory (covers ../ traversal,
absolute paths outside the directory, and symlink escape, since
Path.resolve() follows symlinks before the containment check runs).
"""
from pathlib import Path

import pytest

from api.services.knowledge import ingest as ingest_module


@pytest.fixture
def knowledge_dir(tmp_path, monkeypatch):
    base = tmp_path / "knowledge"
    base.mkdir()
    nested = base / "nested"
    nested.mkdir()
    monkeypatch.setattr(ingest_module, "_KNOWLEDGE_BASE_DIR", base.resolve())

    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.md").write_text("---\nreview_status: approved\n---\nshould never be read")

    return {"base": base, "nested": nested, "outside": outside}


def _approved_md(path: Path, slug_hint="doc"):
    path.write_text(
        f"---\nreview_status: approved\ntitle: {slug_hint}\n---\nBody content for {slug_hint}."
    )


def test_approved_file_inside_base_directory_is_allowed(knowledge_dir):
    target = knowledge_dir["base"] / "hydration.md"
    _approved_md(target, "hydration")
    result = ingest_module.ingest_file(str(target))
    assert result["status"] == "ok", result


def test_nested_valid_file_inside_base_directory_is_allowed(knowledge_dir):
    target = knowledge_dir["nested"] / "sub.md"
    _approved_md(target, "sub")
    result = ingest_module.ingest_file(str(target))
    assert result["status"] == "ok", result


def test_relative_traversal_escape_is_rejected(knowledge_dir):
    escape_path = str(knowledge_dir["base"] / ".." / "outside" / "secret.md")
    result = ingest_module.ingest_file(escape_path)
    assert result["status"] == "error"
    assert "knowledge" in result["reason"].lower()


def test_absolute_path_outside_base_directory_is_rejected(knowledge_dir):
    result = ingest_module.ingest_file(str(knowledge_dir["outside"] / "secret.md"))
    assert result["status"] == "error"
    assert "knowledge" in result["reason"].lower()


def test_symlink_escape_is_rejected(knowledge_dir):
    link = knowledge_dir["base"] / "escape.md"
    link.symlink_to(knowledge_dir["outside"] / "secret.md")
    result = ingest_module.ingest_file(str(link))
    assert result["status"] == "error"
    assert "knowledge" in result["reason"].lower()


def test_file_not_found_inside_base_directory_still_reports_not_found(knowledge_dir):
    missing = knowledge_dir["base"] / "does-not-exist.md"
    result = ingest_module.ingest_file(str(missing))
    assert result["status"] == "error"
    assert "not found" in result["reason"].lower()
