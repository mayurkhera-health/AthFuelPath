"""api/main.py — /docs, /redoc, /openapi.json must not be reachable in
production (Security Item 3, F3). Prior behavior: FastAPI() had no
docs_url/redoc_url/openapi_url override, so the auto-generated docs (full
route map, including admin/coach/knowledge-admin paths) were live
unauthenticated in every environment, and /api/info even advertised the
/docs link.

_docs_enabled(environment) is the pure decision function api/main.py's
FastAPI(...) construction call is built from — testing it directly avoids
needing to reload the whole app module per environment. The suite's own
ENVIRONMENT=test default (see conftest.py) proves the non-production side:
api.main.app is already built under that environment, so its docs_url/
redoc_url/openapi_url being the real paths (not None) is direct evidence
that test/dev environments keep documentation.
"""
from api import main as main_module


def test_docs_enabled_returns_false_for_production():
    assert main_module._docs_enabled("production") is False
    assert main_module._docs_enabled("PRODUCTION") is False


def test_docs_enabled_returns_true_for_development_and_test():
    assert main_module._docs_enabled("development") is True
    assert main_module._docs_enabled("test") is True


def test_docs_enabled_defaults_to_production_safe_when_unset(monkeypatch):
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    assert main_module._docs_enabled() is False


def test_app_built_under_the_test_suites_environment_keeps_docs_available():
    """The test suite runs with ENVIRONMENT=test (conftest.py) — the actual
    app instance built under that environment must have real docs URLs, not
    None, proving non-production environments retain documentation."""
    assert main_module.app.docs_url == "/docs"
    assert main_module.app.redoc_url == "/redoc"
    assert main_module.app.openapi_url == "/openapi.json"


def test_api_info_advertises_docs_link_when_docs_are_enabled():
    body = main_module.root()
    assert body.get("docs") == "/docs"


def test_api_info_omits_docs_link_when_docs_are_disabled(monkeypatch):
    monkeypatch.setattr(main_module, "_DOCS_ENABLED", False)
    body = main_module.root()
    assert "docs" not in body
