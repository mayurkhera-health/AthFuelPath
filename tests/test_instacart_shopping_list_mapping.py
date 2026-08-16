"""Unit tests for Instacart request mapping, validation, and URL/secret safety —
no HTTP involved. See tests/test_instacart_shopping_list_route.py for the
end-to-end route tests against a mocked Instacart client."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from pydantic import ValidationError

from api.services import instacart_client
from api.services.instacart_shopping_list import (
    ShoppingListCreateRequest,
    ShoppingListItemRequest,
    _map_to_instacart_payload,
    _validate_response_url,
    normalize_unit,
)


def _req(**overrides):
    base = {
        "athlete_id": 1,
        "title": "Weekly groceries",
        "items": [{"name": "whole milk", "quantity": 1, "unit": "gallon"}],
    }
    base.update(overrides)
    return ShoppingListCreateRequest(**base)


# ── Unit normalization ────────────────────────────────────────────────────────

def test_normalize_unit_resolves_synonym():
    assert normalize_unit("gallon") == "gal"
    assert normalize_unit("Tablespoons") == "tb"


def test_normalize_unit_accepts_documented_code_directly():
    assert normalize_unit("each") == "each"


def test_normalize_unit_rejects_unsupported_unit():
    with pytest.raises(ValueError):
        normalize_unit("smidge")


# ── Request validation ───────────────────────────────────────────────────────

def test_empty_items_rejected():
    with pytest.raises(ValidationError):
        _req(items=[])


def test_too_many_items_rejected():
    items = [{"name": f"item {i}"} for i in range(51)]
    with pytest.raises(ValidationError):
        _req(items=items)


def test_blank_name_rejected():
    with pytest.raises(ValidationError):
        _req(items=[{"name": "   "}])


def test_name_length_limit_enforced():
    with pytest.raises(ValidationError):
        _req(items=[{"name": "x" * 201}])


def test_invalid_quantity_rejected():
    with pytest.raises(ValidationError):
        _req(items=[{"name": "milk", "quantity": 0}])
    with pytest.raises(ValidationError):
        _req(items=[{"name": "milk", "quantity": -1}])


def test_invalid_upc_format_rejected():
    with pytest.raises(ValidationError):
        _req(items=[{"name": "milk", "upc": "123"}])


def test_valid_upc_accepted():
    req = _req(items=[{"name": "milk", "upc": "012345678905"}])
    assert req.items[0].upc == "012345678905"


def test_control_characters_rejected():
    with pytest.raises(ValidationError):
        _req(title="Weekly\x00groceries")
    with pytest.raises(ValidationError):
        _req(items=[{"name": "milk\x01"}])


def test_duplicate_item_names_rejected():
    with pytest.raises(ValidationError):
        _req(items=[{"name": "Milk"}, {"name": "milk"}])


def test_duplicate_upcs_rejected():
    with pytest.raises(ValidationError):
        _req(items=[
            {"name": "milk", "upc": "012345678905"},
            {"name": "milk 2%", "upc": "012345678905"},
        ])


def test_brand_preferences_limit_enforced():
    with pytest.raises(ValidationError):
        _req(items=[{"name": "milk", "brand_preferences": [f"brand{i}" for i in range(11)]}])


# ── Mapping to Instacart's schema ────────────────────────────────────────────

def test_mapping_uses_line_item_measurements_not_deprecated_fields():
    req = _req(items=[{"name": "whole milk", "quantity": 2, "unit": "gallon"}])
    payload = _map_to_instacart_payload(req)
    item = payload["line_items"][0]
    assert "quantity" not in item and "unit" not in item
    assert item["line_item_measurements"] == [{"quantity": 2, "unit": "gal"}]


def test_mapping_includes_upc_when_present():
    req = _req(items=[{"name": "milk", "upc": "012345678905"}])
    payload = _map_to_instacart_payload(req)
    assert payload["line_items"][0]["upcs"] == ["012345678905"]


def test_mapping_includes_brand_filters_when_present():
    req = _req(items=[{"name": "milk", "brand_preferences": ["Organic Valley"]}])
    payload = _map_to_instacart_payload(req)
    assert payload["line_items"][0]["filters"] == {"brand_filters": ["Organic Valley"]}


def test_mapping_never_includes_client_supplied_base_url_or_headers():
    req = _req()
    payload = _map_to_instacart_payload(req)
    assert "base_url" not in payload
    assert "headers" not in payload
    assert "Authorization" not in payload


def test_partner_linkback_url_comes_from_env_not_request(monkeypatch):
    monkeypatch.setenv("INSTACART_PARTNER_LINKBACK_URL", "https://athfuelpath.example.com/back")
    req = _req()
    payload = _map_to_instacart_payload(req)
    assert payload["landing_page_configuration"]["partner_linkback_url"] == "https://athfuelpath.example.com/back"


# ── Response URL validation ──────────────────────────────────────────────────

def test_trusted_instacart_url_accepted():
    url = "https://www.instacart.com/store/partner_recipe/abc123"
    assert _validate_response_url(url) == url


def test_non_https_url_rejected():
    with pytest.raises(instacart_client.InstacartUnavailableError):
        _validate_response_url("http://www.instacart.com/store/x")


def test_untrusted_host_rejected():
    with pytest.raises(instacart_client.InstacartUnavailableError):
        _validate_response_url("https://evil.example.com/instacart.com")


# ── Secret redaction ─────────────────────────────────────────────────────────

def test_api_key_never_appears_in_error_messages(monkeypatch):
    monkeypatch.setenv("INSTACART_API_KEY", "super-secret-value-12345")

    class _FakeResp:
        status_code = 401
        def json(self):
            return {}

    monkeypatch.setattr(instacart_client.requests, "post", lambda *a, **kw: _FakeResp())

    with pytest.raises(instacart_client.InstacartAuthError) as excinfo:
        instacart_client.create_shopping_list_page({"title": "x", "line_items": []})
    assert "super-secret-value-12345" not in str(excinfo.value)
