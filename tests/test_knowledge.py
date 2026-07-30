import sqlite3
import pytest
import json
from pathlib import Path
import sys, os
sys.path.insert(0, str(Path(__file__).parent.parent))

DB_PATH = Path(__file__).parent.parent / "fuelup.db"


@pytest.fixture(autouse=True)
def _ensure_knowledge_schema():
    from api.startup import ensure_schema
    ensure_schema()

def test_knowledge_tables_exist():
    """DB must have knowledge_items and knowledge_chunks tables."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    tables = {r["name"] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}
    conn.close()
    assert "knowledge_items" in tables
    assert "knowledge_chunks" in tables

def test_knowledge_items_schema():
    """knowledge_items must have required columns."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    cols = {r["name"] for r in conn.execute(
        "PRAGMA table_info(knowledge_items)"
    ).fetchall()}
    conn.close()
    required = {"id", "slug", "title", "category", "source", "source_urls",
                "last_reviewed_date", "applicable_age_range", "tags",
                "review_status", "version", "file_path", "ingested_at"}
    assert required.issubset(cols)

def test_knowledge_chunks_schema():
    """knowledge_chunks must have required columns."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    cols = {r["name"] for r in conn.execute(
        "PRAGMA table_info(knowledge_chunks)"
    ).fetchall()}
    conn.close()
    required = {"id", "item_id", "chunk_index", "heading", "content", "created_at"}
    assert required.issubset(cols)
    assert "embedding" in cols
    assert "embedding_model" in cols


def _get_conn():
    import sqlite3
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn

def test_ingest_creates_knowledge_item():
    """Ingesting an approved file creates a knowledge_items row."""
    from api.services.knowledge.ingest import ingest_file
    iron_path = Path(__file__).parent.parent / "knowledge" / "iron_magnesium.md"
    ingest_file(str(iron_path))
    conn = _get_conn()
    row = conn.execute(
        "SELECT * FROM knowledge_items WHERE slug = 'iron_magnesium'"
    ).fetchone()
    conn.close()
    assert row is not None
    assert row["title"] == "Iron and Magnesium Requirements for Youth Athletes"
    assert row["review_status"] == "approved"

def test_ingest_creates_chunks():
    """Ingesting a file creates at least 3 chunks in knowledge_chunks."""
    conn = _get_conn()
    item = conn.execute(
        "SELECT id FROM knowledge_items WHERE slug = 'iron_magnesium'"
    ).fetchone()
    if not item:
        from api.services.knowledge.ingest import ingest_file
        iron_path = Path(__file__).parent.parent / "knowledge" / "iron_magnesium.md"
        ingest_file(str(iron_path))
        conn = _get_conn()
        item = conn.execute(
            "SELECT id FROM knowledge_items WHERE slug = 'iron_magnesium'"
        ).fetchone()
    chunks = conn.execute(
        "SELECT * FROM knowledge_chunks WHERE item_id = ?", (item["id"],)
    ).fetchall()
    conn.close()
    assert len(chunks) >= 3

def test_draft_file_not_ingested(tmp_path):
    """A file with review_status: draft must not be ingested."""
    draft = tmp_path / "draft_test.md"
    draft.write_text("""---
title: "Draft Test"
category: "test"
source: "test"
source_urls: []
last_reviewed_date: "2026-06-10"
applicable_age_range: "9-17"
tags: ["test"]
review_status: "draft"
version: 1
---

## Test Content

This should never be ingested.
""")
    from api.services.knowledge.ingest import ingest_file
    result = ingest_file(str(draft))
    assert result["status"] == "skipped"
    assert "draft" in result["reason"]


def test_retrieval_finds_iron_content():
    """Query about iron needs should return chunks from iron_magnesium.md."""
    from api.services.knowledge.ingest import ingest_file
    iron_path = Path(__file__).parent.parent / "knowledge" / "iron_magnesium.md"
    ingest_file(str(iron_path))

    from api.services.knowledge.retrieval import retrieve

    def fake_embed(text: str):
        if "iron" in text.lower():
            return [1.0, 0.0, 0.0]
        return [0.0, 1.0, 0.0]

    with patch("api.services.knowledge.retrieval.embed_text", side_effect=fake_embed):
        with patch("api.services.knowledge.retrieval.search_approved_sites", return_value=[]):
            with patch("api.services.knowledge.embedding_utils.embed_text", side_effect=fake_embed):
                results = retrieve("how much iron does a teenage girl need per day")
    assert len(results) > 0
    titles = [r.title for r in results]
    assert any("Iron" in t or "Magnesium" in t for t in titles)

def test_retrieval_returns_empty_for_unknown_domain():
    """Out-of-domain query should return no chunks above threshold."""
    from api.services.knowledge.retrieval import retrieve

    with patch("api.services.knowledge.retrieval.embed_text", return_value=[1.0, 0.0, 0.0]):
        with patch("api.services.knowledge.retrieval._load_local_rows", return_value=[]):
            with patch("api.services.knowledge.retrieval.search_approved_sites", return_value=[]):
                results = retrieve("what is the latest iPhone model price")
    assert results == []

def test_retrieval_respects_approved_only():
    """Only approved chunks are returned."""
    from api.services.knowledge.retrieval import retrieve

    def fake_embed(text: str):
        return [1.0, 0.0] if "draft" in text.lower() else [0.0, 1.0]

    with patch("api.services.knowledge.retrieval.embed_text", side_effect=fake_embed):
        with patch("api.services.knowledge.retrieval.search_approved_sites", return_value=[]):
            with patch("api.services.knowledge.embedding_utils.embed_text", side_effect=fake_embed):
                results = retrieve("test draft content should never appear")
    for r in results:
        assert r.review_status == "approved"


def test_iron_rda_female_14():
    """Female age 14 iron RDA is 15mg per NIH."""
    from api.services.knowledge.calculations import iron_rda
    result = iron_rda(14, "female")
    assert result["value"] == 15
    assert result["unit"] == "mg/day"
    assert "NIH" in result["source"]

def test_iron_rda_male_14():
    """Male age 14 iron RDA is 11mg per NIH."""
    from api.services.knowledge.calculations import iron_rda
    result = iron_rda(14, "male")
    assert result["value"] == 11

def test_iron_rda_child_9():
    """Age 9 iron RDA is 8mg regardless of gender per NIH."""
    from api.services.knowledge.calculations import iron_rda
    assert iron_rda(9, "female")["value"] == 8
    assert iron_rda(9, "male")["value"] == 8

def test_calcium_rda_youth():
    """Ages 9-18 calcium RDA is 1300mg per NIH."""
    from api.services.knowledge.calculations import calcium_rda
    result = calcium_rda(14)
    assert result["value"] == 1300
    assert result["unit"] == "mg/day"

def test_protein_range_game_day():
    """120 lb athlete on game day: 1.6-1.8 g/kg = 87-98g."""
    from api.services.knowledge.calculations import protein_range
    result = protein_range(120, "game")
    assert result["min_g"] == 87
    assert result["max_g"] == 98
    assert result["unit"] == "g/day"

def test_hydration_needs_game():
    """120 lb athlete on game day without heat: 80-88 oz."""
    from api.services.knowledge.calculations import hydration_needs
    result = hydration_needs(120, "game", weather_hot=False)
    assert result["min_oz"] == 80
    assert result["max_oz"] == 88

def test_hydration_needs_hot_weather():
    """Hot weather adds 8-16 oz to baseline."""
    from api.services.knowledge.calculations import hydration_needs
    normal = hydration_needs(120, "rest", weather_hot=False)
    hot = hydration_needs(120, "rest", weather_hot=True)
    assert hot["min_oz"] == normal["min_oz"] + 8
    assert hot["max_oz"] == normal["max_oz"] + 16

def test_pre_training_meal_window():
    """Event at 18:00 → full meal by 15:30, snack by 17:00."""
    from api.services.knowledge.calculations import pre_training_meal_window
    result = pre_training_meal_window("18:00")
    assert result["full_meal_by"] == "15:30"
    assert result["snack_by"] == "17:00"

def test_post_training_recovery_window():
    """Event ends at 20:00 → window open 20:00, closes 20:30."""
    from api.services.knowledge.calculations import post_training_recovery_window
    result = post_training_recovery_window("20:00")
    assert result["window_opens"] == "20:00"
    assert result["window_closes"] == "20:30"


from unittest.mock import patch

def test_no_answer_when_empty_retrieval():
    """When no chunks found, return safe fallback string."""
    from api.services.knowledge.answer import answer_with_knowledge

    with patch("api.services.knowledge.answer.retrieve", return_value=[]):
        result = answer_with_knowledge(
            "what is the stock price of Apple",
            {"id": 1, "first_name": "Alex", "age": 14, "gender": "female",
             "weight_lbs": 120, "event_type": "rest"}
        )
    assert "don't have enough approved information" in result["answer"]
    assert result["citations"] == []

def test_citations_included_in_answer():
    """Answers from knowledge base must include at least one citation."""
    from api.services.knowledge.answer import answer_with_knowledge
    from api.services.knowledge.retrieval import KnowledgeChunk

    mock_chunk = KnowledgeChunk(
        chunk_id=1, item_id=1, slug="iron_magnesium",
        title="Iron and Magnesium Requirements",
        category="micronutrients",
        source="American Academy of Pediatrics",
        source_urls=["https://www.aap.org/en/patient-care/healthy-active-living-for-families/"],
        organization_id="aap",
        organization_name="American Academy of Pediatrics",
        organization_url="https://www.aap.org",
        applicable_age_range="9-17", tags=["iron"],
        review_status="approved", heading="Daily Iron Requirements",
        content="Female athletes age 14-18 need 15mg iron per day.",
        score=0.7,
        origin="local",
    )

    with patch("api.services.knowledge.answer.retrieve", return_value=[mock_chunk]):
        with patch("api.services.knowledge.answer._call_bedrock",
                   return_value="Female athletes need 15mg iron. Source: Iron and Magnesium Requirements"):
            result = answer_with_knowledge(
                "how much iron does a girl need",
                {"id": 1, "first_name": "Alex", "age": 14, "gender": "female",
                 "weight_lbs": 120, "event_type": "rest"}
            )
    assert len(result["citations"]) >= 1
    assert result["citations"][0]["title"] == "Iron and Magnesium Requirements"

def test_safety_guardrail_in_system_prompt():
    """Claude system prompt must contain safety guardrail instructions."""
    from api.services.knowledge.answer import _build_system_prompt
    prompt = _build_system_prompt(chunks=[], calc_result=None)
    assert "medical" in prompt.lower()
    assert "professional" in prompt.lower()
    assert "eating" in prompt.lower()
    assert "YOUR CAPABILITIES" in prompt
    assert "Trader Joe" in prompt or "store" in prompt.lower()


def test_build_system_prompt_no_heat_block_without_weather():
    from api.services.knowledge.answer import _build_system_prompt
    assert "HEAT ADVISORY" not in _build_system_prompt(chunks=[], calc_result=None, weather=None)
    cold = {"temp_f": 60.0, "humidity": 40, "heat_flag": False, "heat_level": "none", "location_label": None}
    assert "HEAT ADVISORY" not in _build_system_prompt(chunks=[], calc_result=None, weather=cold)


def test_build_system_prompt_includes_heat_block_when_hot():
    from api.services.knowledge.answer import _build_system_prompt
    hot = {
        "temp_f": 92.0, "humidity": 40, "heat_flag": True, "heat_level": "hot",
        "location_label": "San Jose, CA",
    }
    prompt = _build_system_prompt(chunks=[], calc_result=None, weather=hot)
    assert "HEAT ADVISORY" in prompt
    assert "92.0" in prompt
    assert "San Jose, CA" in prompt


def test_todays_event_uses_now_local_date():
    from api.services.knowledge.answer import _todays_event

    class _FakeConn:
        def execute(self, sql, params):
            self.seen_params = params
            return self
        def fetchone(self):
            return {"event_name": "Big Game", "city": "Stadium City"}
        def close(self):
            pass

    fake_conn = _FakeConn()
    with patch("api.database.get_conn", return_value=fake_conn):
        event = _todays_event(1, "2026-07-23T11:15:00")

    assert event == {"event_name": "Big Game", "city": "Stadium City"}
    assert fake_conn.seen_params == (1, "2026-07-23")


def test_todays_event_falls_back_to_server_date_without_now():
    from datetime import date
    from api.services.knowledge.answer import _todays_event

    class _FakeConn:
        def execute(self, sql, params):
            self.seen_params = params
            return self
        def fetchone(self):
            return None
        def close(self):
            pass

    fake_conn = _FakeConn()
    with patch("api.database.get_conn", return_value=fake_conn):
        event = _todays_event(1, None)

    assert event is None
    assert fake_conn.seen_params == (1, date.today().isoformat())


def test_todays_event_returns_none_on_db_error():
    from api.services.knowledge.answer import _todays_event

    class _BoomConn:
        def execute(self, sql, params):
            raise RuntimeError("db down")
        def close(self):
            pass

    with patch("api.database.get_conn", return_value=_BoomConn()):
        assert _todays_event(1, None) is None


def test_knowledge_answer_includes_weather_when_location_given():
    """now/lat/lon on a plain knowledge question should reach the system
    prompt as a heat advisory when it resolves hot — the actual live path
    the mobile app calls, not the unused /api/coach/chat one."""
    from api.services.knowledge.answer import answer_with_knowledge
    from api.services.knowledge.retrieval import KnowledgeChunk

    mock_chunk = KnowledgeChunk(
        chunk_id=1, item_id=1, slug="hydration",
        title="Hydration for Youth Athletes", category="hydration",
        source="ACSM", source_urls=["https://www.acsm.org"],
        organization_id="acsm", organization_name="ACSM", organization_url="https://www.acsm.org",
        applicable_age_range="9-17", tags=["hydration"],
        review_status="approved", heading=None,
        content="Drink water regularly during activity.", score=0.7, origin="local",
    )
    hot_weather = {
        "temp_f": 92.0, "humidity": 40, "heat_flag": True, "heat_level": "hot",
        "location_label": "San Jose, CA",
    }

    with patch("api.services.knowledge.answer._classify_coach_path",
               return_value={"path": "knowledge", "recipe_category": None}):
        with patch("api.services.knowledge.answer.retrieve", return_value=[mock_chunk]):
            with patch("api.services.knowledge.answer._todays_event", return_value=None) as mock_event:
                with patch("api.services.weather.resolve_weather", return_value=hot_weather) as mock_resolve:
                    with patch("api.services.knowledge.answer.is_configured", return_value=True):
                        with patch("api.services.knowledge.answer.converse_text") as mock_converse:
                            mock_converse.return_value = "Stay hydrated!"
                            answer_with_knowledge(
                                "How much water should I drink?",
                                {"id": 1, "first_name": "Alex", "age": 14, "gender": "female", "weight_lbs": 120},
                                now="2026-07-23T14:00:00",
                                latitude=37.33, longitude=-121.89,
                            )

    mock_event.assert_called_once_with(1, "2026-07-23T14:00:00")
    mock_resolve.assert_called_once_with(None, 37.33, -121.89)
    system_prompt = mock_converse.call_args.kwargs["system"]
    assert "HEAT ADVISORY" in system_prompt
    assert "San Jose, CA" in system_prompt


def test_knowledge_answer_skips_weather_lookup_without_location():
    """No now/lat/lon on the request -> zero weather-related calls. Must not
    regress the existing no-location flow with wasted DB/geocode work."""
    from api.services.knowledge.answer import answer_with_knowledge
    from api.services.knowledge.retrieval import KnowledgeChunk

    mock_chunk = KnowledgeChunk(
        chunk_id=1, item_id=1, slug="hydration",
        title="Hydration for Youth Athletes", category="hydration",
        source="ACSM", source_urls=["https://www.acsm.org"],
        organization_id="acsm", organization_name="ACSM", organization_url="https://www.acsm.org",
        applicable_age_range="9-17", tags=["hydration"],
        review_status="approved", heading=None,
        content="Drink water regularly during activity.", score=0.7, origin="local",
    )

    with patch("api.services.knowledge.answer._classify_coach_path",
               return_value={"path": "knowledge", "recipe_category": None}):
        with patch("api.services.knowledge.answer.retrieve", return_value=[mock_chunk]):
            with patch("api.services.knowledge.answer._todays_event") as mock_event:
                with patch("api.services.knowledge.answer.is_configured", return_value=True):
                    with patch("api.services.knowledge.answer.converse_text", return_value="ok") as mock_converse:
                        answer_with_knowledge(
                            "How much water should I drink?",
                            {"id": 1, "first_name": "Alex", "age": 14, "gender": "female", "weight_lbs": 120},
                        )

    mock_event.assert_not_called()
    assert "HEAT ADVISORY" not in mock_converse.call_args.kwargs["system"]


def test_knowledge_answer_survives_null_humidity_end_to_end():
    """The actual production crash, reproduced through the real call chain
    (not just the isolated weather.py unit) — a null-humidity API response
    must not 500 the whole coach answer. Only mocks the network boundary
    (_fetch_weather); resolve_weather/weather_context run for real."""
    from api.services.knowledge.answer import answer_with_knowledge
    from api.services.knowledge.retrieval import KnowledgeChunk

    mock_chunk = KnowledgeChunk(
        chunk_id=1, item_id=1, slug="hydration",
        title="Hydration for Youth Athletes", category="hydration",
        source="ACSM", source_urls=["https://www.acsm.org"],
        organization_id="acsm", organization_name="ACSM", organization_url="https://www.acsm.org",
        applicable_age_range="9-17", tags=["hydration"],
        review_status="approved", heading=None,
        content="Drink water regularly during activity.", score=0.7, origin="local",
    )

    with patch("api.services.knowledge.answer._classify_coach_path",
               return_value={"path": "knowledge", "recipe_category": None}):
        with patch("api.services.knowledge.answer.retrieve", return_value=[mock_chunk]):
            with patch("api.services.knowledge.answer._todays_event", return_value=None):
                with patch(
                    "api.services.weather._fetch_weather",
                    return_value={"temp_f": 92.0, "humidity": None, "description": "hazy", "error": None},
                ):
                    with patch("api.services.weather.reverse_geocode_city", return_value=None):
                        with patch("api.services.knowledge.answer.is_configured", return_value=True):
                            with patch(
                                "api.services.knowledge.answer.converse_text", return_value="Stay hydrated!"
                            ) as mock_converse:
                                result = answer_with_knowledge(
                                    "How much water should I drink?",
                                    {"id": 1, "first_name": "Alex", "age": 14, "gender": "female", "weight_lbs": 120},
                                    now="2026-07-23T14:00:00",
                                    latitude=37.33, longitude=-121.89,
                                )

    assert result["answer"] == "Stay hydrated!"
    system_prompt = mock_converse.call_args.kwargs["system"]
    assert "HEAT ADVISORY" in system_prompt   # still classified hot via the 50% humidity default


def test_classifier_system_prompt_documents_capabilities():
    from api.services.knowledge.answer import _CLASSIFIER_SYSTEM
    assert "out_of_scope" in _CLASSIFIER_SYSTEM
    assert "recipe" in _CLASSIFIER_SYSTEM
    assert "knowledge" in _CLASSIFIER_SYSTEM


def test_classify_coach_path_parses_out_of_scope_route():
    from api.services.knowledge.answer import _classify_coach_path

    with patch("api.services.knowledge.answer.is_configured", return_value=True):
        with patch("api.services.knowledge.answer.converse_text", return_value='{"path": "out_of_scope", "recipe_category": null}'):
            route = _classify_coach_path(
                "What should I eat at Trader Joe's?",
                {"first_name": "Alex", "age": 14},
            )
    assert route == {"path": "out_of_scope", "recipe_category": None, "restaurant_name": None, "location_text": None}


def test_coach_routes_out_of_scope_without_retrieval():
    from api.services.knowledge.answer import answer_with_knowledge

    with patch("api.services.knowledge.answer._classify_coach_path", return_value={"path": "out_of_scope", "recipe_category": None}):
        with patch("api.services.knowledge.answer.is_configured", return_value=True):
            with patch("api.services.knowledge.answer.converse_text", return_value="I don't know what's at Trader Joe's — **tell me what you see** and I'll help you pick."):
                with patch("api.services.knowledge.answer.retrieve") as mock_retrieve:
                    result = answer_with_knowledge(
                        "What should I eat at Trader Joe's?",
                        {"id": 1, "first_name": "Alex", "age": 14, "gender": "female", "weight_lbs": 120},
                    )
    mock_retrieve.assert_not_called()
    assert "Trader Joe" in result["answer"]
    assert result["citations"] == []

def test_classify_coach_path_parses_recipe_route():
    from api.services.knowledge.answer import _classify_coach_path

    with patch("api.services.knowledge.answer.is_configured", return_value=True):
        with patch("api.services.knowledge.answer.converse_text", return_value='{"path": "recipe", "recipe_category": "post_game"}'):
            route = _classify_coach_path(
                "Make me something for after the game",
                {"first_name": "Alex", "age": 14},
            )
    assert route == {"path": "recipe", "recipe_category": "post_game", "restaurant_name": None, "location_text": None}


def test_classify_coach_path_parses_restaurant_route():
    from api.services.knowledge.answer import _classify_coach_path

    with patch("api.services.knowledge.answer.is_configured", return_value=True):
        with patch(
            "api.services.knowledge.answer.converse_text",
            return_value='{"path": "restaurant", "recipe_category": null, "restaurant_name": "Panda Express"}',
        ):
            route = _classify_coach_path(
                "I am heading to Panda Express for lunch, what should I get?",
                {"first_name": "Alex", "age": 14},
            )
    assert route == {"path": "restaurant", "recipe_category": None, "restaurant_name": "Panda Express", "location_text": None}


def test_classify_coach_path_restaurant_without_name_falls_back_to_out_of_scope():
    from api.services.knowledge.answer import _classify_coach_path

    with patch("api.services.knowledge.answer.is_configured", return_value=True):
        with patch(
            "api.services.knowledge.answer.converse_text",
            return_value='{"path": "restaurant", "recipe_category": null, "restaurant_name": ""}',
        ):
            route = _classify_coach_path(
                "What should I get for lunch?",
                {"first_name": "Alex", "age": 14},
            )
    assert route == {"path": "out_of_scope", "recipe_category": None, "restaurant_name": None, "location_text": None}


def test_classify_coach_path_parses_meal_macro_route():
    from api.services.knowledge.answer import _classify_coach_path

    with patch("api.services.knowledge.answer.is_configured", return_value=True):
        with patch("api.services.knowledge.answer.converse_text", return_value='{"path": "meal_macro"}'):
            route = _classify_coach_path(
                "I had 2 eggs and toast for breakfast, how many calories was that?",
                {"first_name": "Alex", "age": 14},
            )
    assert route == {"path": "meal_macro", "recipe_category": None, "restaurant_name": None, "location_text": None}


def test_classify_coach_path_meal_macro_needs_no_explicit_number_ask():
    """Just describing what was eaten is enough — product decision 2026-07-29
    changed this from requiring an explicit calorie/macro ask."""
    from api.services.knowledge.answer import _classify_coach_path

    with patch("api.services.knowledge.answer.is_configured", return_value=True):
        with patch("api.services.knowledge.answer.converse_text", return_value='{"path": "meal_macro"}'):
            route = _classify_coach_path(
                "I had 2 eggs and toast for breakfast",
                {"first_name": "Alex", "age": 14},
            )
    assert route["path"] == "meal_macro"


def test_classify_coach_path_defaults_to_knowledge_on_bad_json():
    from api.services.knowledge.answer import _classify_coach_path

    with patch("api.services.knowledge.answer.is_configured", return_value=True):
        with patch("api.services.knowledge.answer.converse_text", return_value="not json"):
            route = _classify_coach_path(
                "How much iron do I need?",
                {"first_name": "Alex", "age": 14},
            )
    assert route == {"path": "knowledge", "recipe_category": None, "restaurant_name": None, "location_text": None}


def test_coach_routes_recipe_requests():
    """Recipe-style questions should invoke the recipe generator, not RAG."""
    from api.services.knowledge.answer import answer_with_knowledge

    mock_recipe = {
        "recipe": {
            "name": "Quick Halftime Bites",
            "category": "halftime",
            "calories": 180,
            "protein_g": 3,
            "carbs_g": 40,
            "fat_g": 1,
            "ingredients": ["1 banana", "2 tbsp honey"],
            "preparation_notes": "Slice and serve.",
            "tags": ["halftime"],
        },
        "source_ingredients": ["Bananas, raw"],
    }

    with patch("api.services.knowledge.answer._classify_coach_path", return_value={"path": "recipe", "recipe_category": "halftime"}):
        with patch("api.services.recipe_generator.generate_recipe_options") as mock_gen:
            mock_gen.return_value = {
                "recipes": [{"recipe": mock_recipe["recipe"], "source_ingredients": mock_recipe["source_ingredients"]}],
                "recipe": mock_recipe["recipe"],
                "source_ingredients": mock_recipe["source_ingredients"],
                "ingredient_source": "recipe_library",
            }
            result = answer_with_knowledge(
                "Generate a halftime snack recipe for me",
                {
                    "id": 1,
                    "first_name": "Alex",
                    "age": 14,
                    "gender": "female",
                    "weight_lbs": 120,
                    "allergies": "[]",
                    "dietary_restrictions": None,
                },
            )

    assert result["intent"] == "recipe"
    assert result["recipe"]["name"] == "Quick Halftime Bites"
    assert result["source_ingredients"] == ["Bananas, raw"]
    assert "halftime" in result["answer"].lower()


def test_coach_routes_meal_macro_requests_to_real_food_lookup():
    """A described meal + explicit macro ask should hit voice_meal_analyzer's
    real USDA lookup, not the LLM inventing numbers."""
    from api.services.knowledge.answer import answer_with_knowledge

    mock_analysis = {
        "foods": [
            {"name": "scrambled eggs", "estimated_portion_g": 100, "calories": 150,
             "protein_g": 12.0, "carbs_g": 1.0, "fat_g": 10.0, "fdc_id": 123, "fdc_description": "Eggs, scrambled"},
            {"name": "toast", "estimated_portion_g": 30, "calories": 80,
             "protein_g": 3.0, "carbs_g": 15.0, "fat_g": 1.0, "fdc_id": 456, "fdc_description": "Bread, toasted"},
        ],
        "totals": {"calories": 230, "protein_g": 15.0, "carbs_g": 16.0, "fat_g": 11.0},
        "description": "scrambled eggs (~100g), toast (~30g)",
        "transcription": "I had scrambled eggs and toast",
    }

    with patch("api.services.knowledge.answer._classify_coach_path", return_value={"path": "meal_macro", "recipe_category": None, "restaurant_name": None, "location_text": None}):
        with patch("api.services.voice_meal_analyzer.analyze_voice", return_value=mock_analysis) as mock_analyze:
            result = answer_with_knowledge(
                "I had scrambled eggs and toast, how many calories was that?",
                {"id": 1, "first_name": "Alex", "age": 14, "gender": "female",
                 "weight_lbs": 120, "allergies": "[]", "dietary_restrictions": None},
            )

    mock_analyze.assert_called_once()
    assert result["intent"] == "meal_macro"
    assert result["meal_analysis"] == mock_analysis
    assert "230" in result["answer"]
    assert "16.0g carbs" in result["answer"]
    assert "15.0g protein" in result["answer"]
    assert "11.0g fat" in result["answer"]


def test_coach_meal_macro_falls_back_gracefully_when_no_food_detected():
    from api.services.knowledge.answer import answer_with_knowledge

    with patch("api.services.knowledge.answer._classify_coach_path", return_value={"path": "meal_macro", "recipe_category": None, "restaurant_name": None, "location_text": None}):
        with patch("api.services.voice_meal_analyzer.analyze_voice", side_effect=ValueError("No foods detected in the description.")):
            result = answer_with_knowledge(
                "how many calories was that",
                {"id": 1, "first_name": "Alex", "age": 14, "gender": "female",
                 "weight_lbs": 120, "allergies": "[]", "dietary_restrictions": None},
            )

    assert result["intent"] == "meal_macro"
    assert result["meal_analysis"] is None
    assert "couldn't quite tell" in result["answer"].lower()


def test_coach_meal_macro_states_assumed_portions_without_asking_back():
    """Product decision 2026-07-29 (v2): no clarifying-question round-trip —
    an earlier ask-first version was too naggy. Always proceeds straight to
    the real lookup and states the assumed portions in the answer so the
    athlete can correct them conversationally instead of being blocked."""
    from api.services.knowledge.answer import answer_with_knowledge

    mock_analysis = {
        "foods": [{"name": "rice", "estimated_portion_g": 150, "calories": 200,
                    "protein_g": 4.0, "carbs_g": 44.0, "fat_g": 0.5, "fdc_id": 1, "fdc_description": "Rice"}],
        "totals": {"calories": 200, "protein_g": 4.0, "carbs_g": 44.0, "fat_g": 0.5},
        "description": "rice (~150g)",
        "transcription": "I had some rice and chicken",
    }

    with patch("api.services.knowledge.answer._classify_coach_path", return_value={"path": "meal_macro", "recipe_category": None, "restaurant_name": None, "location_text": None}):
        with patch("api.services.voice_meal_analyzer.analyze_voice", return_value=mock_analysis) as mock_analyze:
            result = answer_with_knowledge(
                "I had some rice and chicken",
                {"id": 1, "first_name": "Alex", "age": 14, "gender": "female",
                 "weight_lbs": 120, "allergies": "[]", "dietary_restrictions": None},
            )

    mock_analyze.assert_called_once()
    assert result["meal_analysis"] == mock_analysis
    assert "rice (~150g)" in result["answer"]
    assert "bigger or smaller" in result["answer"].lower()


def test_coach_skips_recipe_for_general_questions():
    """General fueling questions should not trigger recipe generation."""
    from api.services.knowledge.answer import answer_with_knowledge

    with patch("api.services.knowledge.answer._classify_coach_path", return_value={"path": "knowledge", "recipe_category": None}):
        with patch("api.services.recipe_generator.generate_recipe_options") as mock_gen:
            with patch("api.services.knowledge.answer.retrieve", return_value=[]):
                answer_with_knowledge(
                    "What should I eat before a game?",
                    {"id": 1, "first_name": "Alex", "age": 14, "gender": "female", "weight_lbs": 120},
                )
    mock_gen.assert_not_called()


def test_coach_routes_restaurant_requests():
    """Naming a specific restaurant should search that restaurant's own menu, not RAG."""
    from api.services.knowledge.answer import answer_with_knowledge
    from api.services.knowledge.web_search import RestaurantSearchResult

    mock_results = [
        RestaurantSearchResult(
            url="https://www.pandaexpress.com/menu",
            title="Panda Express Menu",
            snippet="Grilled Teriyaki Chicken, Broccoli Beef, Fried Rice, Chow Mein",
            content="Grilled Teriyaki Chicken, Broccoli Beef, Fried Rice, Chow Mein",
            score=0.9,
        )
    ]

    with patch(
        "api.services.knowledge.answer._classify_coach_path",
        return_value={"path": "restaurant", "recipe_category": None, "restaurant_name": "Panda Express"},
    ):
        with patch("api.services.knowledge.answer.is_configured", return_value=True):
            with patch(
                "api.services.knowledge.web_search.search_restaurant_menu", return_value=mock_results
            ):
                with patch(
                    "api.services.knowledge.answer.converse_text",
                    return_value="**Grilled Teriyaki Chicken** with a side of veggies is your best bet.",
                ) as mock_converse:
                    with patch("api.services.knowledge.answer.retrieve") as mock_retrieve:
                        result = answer_with_knowledge(
                            "I am heading to Panda Express for lunch, what should I get?",
                            {"id": 1, "first_name": "Alex", "age": 14, "gender": "female", "weight_lbs": 120},
                        )

    mock_retrieve.assert_not_called()
    assert result["intent"] == "restaurant"
    assert "Grilled Teriyaki Chicken" in result["answer"]
    assert result["restaurant_sources"][0]["url"] == "https://www.pandaexpress.com/menu"
    # menu excerpts must reach the system prompt, not just the user question
    system_prompt = mock_converse.call_args.kwargs["system"]
    assert "Panda Express" in system_prompt
    assert "Grilled Teriyaki Chicken" in system_prompt


def test_restaurant_answer_leads_with_name_and_address_when_matched():
    """The parent's ask: the coach's top-level restaurant answer should lead
    with the restaurant's name and a verified address, not bury it in prose."""
    from api.services.knowledge.answer import answer_with_knowledge
    from api.services.knowledge.web_search import RestaurantSearchResult
    from api.services.places.nearby_search import PlaceCandidate

    mock_results = [
        RestaurantSearchResult(
            url="https://www.pandaexpress.com/menu", title="Panda Express Menu",
            snippet="", content="Grilled Teriyaki Chicken, Broccoli Beef", score=0.9,
        )
    ]
    mock_place = PlaceCandidate(
        place_id="p1", name="Panda Express", distance_m=500,
        address="123 Main St, San Jose, CA", category="Chinese", rating=8.0,
        review_count=100, price_level=2, open_now=True, website=None, maps_url=None,
    )

    with patch(
        "api.services.knowledge.answer._classify_coach_path",
        return_value={"path": "restaurant", "recipe_category": None, "restaurant_name": "Panda Express"},
    ):
        with patch("api.services.knowledge.answer.is_configured", return_value=True):
            with patch("api.services.knowledge.web_search.search_restaurant_menu", return_value=mock_results):
                with patch("api.services.knowledge.answer.converse_text", return_value="Get the grilled option."):
                    with patch(
                        "api.services.places.nearby_search.find_restaurant_by_name",
                        return_value=mock_place,
                    ) as mock_find:
                        result = answer_with_knowledge(
                            "I am heading to Panda Express for lunch, what should I get?",
                            {"id": 1, "first_name": "Alex", "age": 14},
                            latitude=37.33, longitude=-121.89,
                        )

    mock_find.assert_called_once_with("Panda Express", 37.33, -121.89, 1)
    assert result["answer"].startswith("**Panda Express** — 123 Main St, San Jose, CA\n\n")
    assert "Get the grilled option." in result["answer"]


def test_restaurant_answer_leads_with_name_only_without_coords():
    """No device location on the request -> name-only header, never a
    Foursquare lookup attempt (nothing to look up near)."""
    from api.services.knowledge.answer import answer_with_knowledge
    from api.services.knowledge.web_search import RestaurantSearchResult

    mock_results = [
        RestaurantSearchResult(
            url="https://www.pandaexpress.com/menu", title="Panda Express Menu",
            snippet="", content="Grilled Teriyaki Chicken", score=0.9,
        )
    ]

    with patch(
        "api.services.knowledge.answer._classify_coach_path",
        return_value={"path": "restaurant", "recipe_category": None, "restaurant_name": "Panda Express"},
    ):
        with patch("api.services.knowledge.answer.is_configured", return_value=True):
            with patch("api.services.knowledge.web_search.search_restaurant_menu", return_value=mock_results):
                with patch("api.services.knowledge.answer.converse_text", return_value="Get the grilled option."):
                    with patch(
                        "api.services.places.nearby_search.find_restaurant_by_name"
                    ) as mock_find:
                        result = answer_with_knowledge(
                            "What should I get at Panda Express?",
                            {"id": 1, "first_name": "Alex", "age": 14},
                        )

    mock_find.assert_not_called()
    assert result["answer"].startswith("**Panda Express**\n\n")
    assert " — " not in result["answer"].split("\n\n")[0]


def test_restaurant_answer_leads_with_name_only_when_no_confident_match():
    """Coords present but Foursquare has no confident name match -> still
    lead with the name, just skip the address rather than guess."""
    from api.services.knowledge.answer import answer_with_knowledge
    from api.services.knowledge.web_search import RestaurantSearchResult

    mock_results = [
        RestaurantSearchResult(
            url="https://www.pandaexpress.com/menu", title="Panda Express Menu",
            snippet="", content="Grilled Teriyaki Chicken", score=0.9,
        )
    ]

    with patch(
        "api.services.knowledge.answer._classify_coach_path",
        return_value={"path": "restaurant", "recipe_category": None, "restaurant_name": "Panda Express"},
    ):
        with patch("api.services.knowledge.answer.is_configured", return_value=True):
            with patch("api.services.knowledge.web_search.search_restaurant_menu", return_value=mock_results):
                with patch("api.services.knowledge.answer.converse_text", return_value="Get the grilled option."):
                    with patch(
                        "api.services.places.nearby_search.find_restaurant_by_name",
                        return_value=None,
                    ):
                        result = answer_with_knowledge(
                            "What should I get at Panda Express?",
                            {"id": 1, "first_name": "Alex", "age": 14},
                            latitude=37.33, longitude=-121.89,
                        )

    assert result["answer"].startswith("**Panda Express**\n\n")


def test_meal_period_from_time_boundaries():
    from datetime import datetime
    from api.services.knowledge.answer import _meal_period_from_time

    assert _meal_period_from_time(datetime(2026, 7, 22, 7, 0)) == "breakfast"
    # the exact case from the founder's report: 11:15am -> close to lunch
    assert _meal_period_from_time(datetime(2026, 7, 22, 11, 15)) == "lunch"
    assert _meal_period_from_time(datetime(2026, 7, 22, 13, 59)) == "lunch"
    assert _meal_period_from_time(datetime(2026, 7, 22, 15, 30)) == "afternoon snack"
    assert _meal_period_from_time(datetime(2026, 7, 22, 18, 0)) == "dinner"
    assert _meal_period_from_time(datetime(2026, 7, 22, 23, 0)) == "late-night snack"
    assert _meal_period_from_time(datetime(2026, 7, 22, 2, 0)) == "late-night snack"


def test_coach_restaurant_includes_meal_timing_and_location():
    """now + lat/lon should reach the restaurant system prompt as meal-period
    framing and a location-narrowed search — without the caller (route) doing
    any of that derivation itself."""
    from api.services.knowledge.answer import answer_with_knowledge
    from api.services.knowledge.web_search import RestaurantSearchResult

    mock_results = [
        RestaurantSearchResult(
            url="https://www.pandaexpress.com/menu", title="Panda Express Menu",
            snippet="", content="Grilled Teriyaki Chicken, Broccoli Beef", score=0.9,
        )
    ]

    with patch(
        "api.services.knowledge.answer._classify_coach_path",
        return_value={"path": "restaurant", "recipe_category": None, "restaurant_name": "Panda Express"},
    ):
        with patch("api.services.knowledge.answer.is_configured", return_value=True):
            with patch(
                "api.services.weather.reverse_geocode_city", return_value="San Jose, CA"
            ) as mock_geocode:
                with patch(
                    "api.services.knowledge.web_search.search_restaurant_menu",
                    return_value=mock_results,
                ) as mock_search:
                    with patch(
                        "api.services.knowledge.answer.converse_text",
                        return_value="**Grilled Teriyaki Chicken** is your best bet.",
                    ) as mock_converse:
                        answer_with_knowledge(
                            "I am heading to Panda Express for lunch, what should I get?",
                            {"id": 1, "first_name": "Alex", "age": 14, "gender": "female", "weight_lbs": 120},
                            now="2026-07-22T11:15:00",
                            latitude=37.33,
                            longitude=-121.89,
                        )

    mock_geocode.assert_called_once_with(37.33, -121.89)
    mock_search.assert_called_once()
    assert mock_search.call_args.kwargs["city"] == "San Jose, CA"
    system_prompt = mock_converse.call_args.kwargs["system"]
    assert "lunch" in system_prompt.lower()


def test_coach_restaurant_skips_timing_and_location_when_not_given():
    """No now/lat/lon on the request -> no geocode call, no timing block -
    must not break the existing no-location flow."""
    from api.services.knowledge.answer import answer_with_knowledge
    from api.services.knowledge.web_search import RestaurantSearchResult

    mock_results = [
        RestaurantSearchResult(
            url="https://www.pandaexpress.com/menu", title="Panda Express Menu",
            snippet="", content="Grilled Teriyaki Chicken", score=0.9,
        )
    ]

    with patch(
        "api.services.knowledge.answer._classify_coach_path",
        return_value={"path": "restaurant", "recipe_category": None, "restaurant_name": "Panda Express"},
    ):
        with patch("api.services.knowledge.answer.is_configured", return_value=True):
            with patch("api.services.weather.reverse_geocode_city") as mock_geocode:
                with patch(
                    "api.services.knowledge.web_search.search_restaurant_menu",
                    return_value=mock_results,
                ) as mock_search:
                    with patch(
                        "api.services.knowledge.answer.converse_text",
                        return_value="**Grilled Teriyaki Chicken** is your best bet.",
                    ):
                        answer_with_knowledge(
                            "What should I get at Panda Express?",
                            {"id": 1, "first_name": "Alex", "age": 14, "gender": "female", "weight_lbs": 120},
                        )

    mock_geocode.assert_not_called()
    assert mock_search.call_args.kwargs["city"] is None


def test_coach_restaurant_falls_back_when_no_menu_found():
    from api.services.knowledge.answer import answer_with_knowledge

    with patch(
        "api.services.knowledge.answer._classify_coach_path",
        return_value={"path": "restaurant", "recipe_category": None, "restaurant_name": "Some Obscure Diner"},
    ):
        with patch("api.services.knowledge.answer.is_configured", return_value=True):
            with patch("api.services.knowledge.web_search.search_restaurant_menu", return_value=[]):
                result = answer_with_knowledge(
                    "What should I get at Some Obscure Diner?",
                    {"id": 1, "first_name": "Alex", "age": 14, "gender": "female", "weight_lbs": 120},
                )

    assert result["intent"] == "restaurant"
    assert "Some Obscure Diner" in result["answer"]


def test_restaurant_prompt_forbids_hedged_extra_suggestions():
    """Confirmed live: given a real, grounded menu item, the model still
    tacked on an unverified aside ("...or a lettuce wrap if available (though
    not explicitly listed)"). Rule 1 must explicitly forbid this exact
    pattern, not just the "nothing found at all" case — a partial hedge
    alongside a real answer slipped through the original wording."""
    from api.services.knowledge.answer import _RESTAURANT_SYSTEM_TEMPLATE

    prompt = _RESTAURANT_SYSTEM_TEMPLATE.format(
        restaurant_name="Test Diner", timing_block="", excerpts_text="", allergy_block="None",
    )
    assert "though not explicitly listed" in prompt  # the exact forbidden phrase, named
    assert "even as a minor aside" in prompt
    assert "do not mention it" in prompt.lower()


def test_calculation_included_when_relevant():
    """Iron question for a known athlete should produce a non-None result."""
    from api.services.knowledge.answer import answer_with_knowledge
    from api.services.knowledge.retrieval import KnowledgeChunk

    mock_chunk = KnowledgeChunk(
        chunk_id=1, item_id=1, slug="iron_magnesium",
        title="Iron and Magnesium Requirements",
        category="micronutrients",
        source="American Academy of Pediatrics",
        source_urls=["https://www.aap.org"],
        organization_id="aap",
        organization_name="American Academy of Pediatrics",
        organization_url="https://www.aap.org",
        applicable_age_range="9-17", tags=["iron"],
        review_status="approved", heading="Iron RDA",
        content="Female athletes age 14-18 need 15mg iron per day.",
        score=0.6,
        origin="local",
    )

    with patch("api.services.knowledge.answer.retrieve", return_value=[mock_chunk]):
        with patch("api.services.knowledge.answer._call_bedrock", return_value="15mg"):
            result = answer_with_knowledge(
                "how much iron does she need",
                {"id": 1, "first_name": "Maya", "age": 15, "gender": "female",
                 "weight_lbs": 115, "event_type": "rest"}
            )
    assert result["answer"] is not None


# ── persona-aware audience framing ──────────────────────────────────────────

def test_audience_suffix_empty_when_persona_unset():
    from api.services.knowledge.answer import _audience_suffix
    assert _audience_suffix(None, {"first_name": "Alex"}) == ""
    assert _audience_suffix("coach", {"first_name": "Alex"}) == ""  # unrecognized value


def test_audience_suffix_parent_tone():
    from api.services.knowledge.answer import _audience_suffix
    suffix = _audience_suffix("parent", {"first_name": "Alex"})
    assert "Alex's parent/guardian" in suffix
    assert "not the athlete" in suffix


def test_audience_suffix_athlete_tone():
    from api.services.knowledge.answer import _audience_suffix
    suffix = _audience_suffix("athlete", {"first_name": "Alex", "age": 14})
    assert "speaking directly to Alex" in suffix
    assert "age 14" in suffix


def test_build_system_prompt_no_audience_block_without_persona():
    from api.services.knowledge.answer import _build_system_prompt
    prompt = _build_system_prompt(chunks=[], calc_result=None)
    assert "AUDIENCE:" not in prompt


def test_build_system_prompt_includes_persona_audience_block():
    from api.services.knowledge.answer import _build_system_prompt
    prompt = _build_system_prompt(
        chunks=[], calc_result=None, persona="parent", athlete={"first_name": "Jamie"}
    )
    assert "AUDIENCE:" in prompt
    assert "Jamie's parent/guardian" in prompt


def test_knowledge_answer_passes_persona_into_system_prompt():
    """End-to-end: persona sent on the request must reach the Bedrock system
    prompt for the main knowledge-answer path."""
    from api.services.knowledge.answer import answer_with_knowledge
    from api.services.knowledge.retrieval import KnowledgeChunk

    mock_chunk = KnowledgeChunk(
        chunk_id=1, item_id=1, slug="iron_magnesium", title="Iron Requirements",
        category="micronutrients", source="AAP", source_urls=["https://www.aap.org"],
        organization_id="aap", organization_name="AAP", organization_url="https://www.aap.org",
        applicable_age_range="9-17", tags=["iron"], review_status="approved", heading="Iron",
        content="Female athletes need 15mg iron per day.", score=0.7, origin="local",
    )

    with patch("api.services.knowledge.answer.retrieve", return_value=[mock_chunk]):
        with patch("api.services.knowledge.answer._call_bedrock", return_value="15mg") as mock_call:
            answer_with_knowledge(
                "how much iron do I need",
                {"id": 1, "first_name": "Riley", "age": 14, "gender": "female", "weight_lbs": 120},
                persona="athlete",
            )

    system_prompt = mock_call.call_args.args[0]
    assert "speaking directly to Riley" in system_prompt


def test_coach_restaurant_passes_persona_into_system_prompt():
    from api.services.knowledge.answer import answer_with_knowledge
    from api.services.knowledge.web_search import RestaurantSearchResult

    mock_results = [
        RestaurantSearchResult(
            url="https://www.pandaexpress.com/menu", title="Panda Express Menu",
            snippet="", content="Grilled Teriyaki Chicken", score=0.9,
        )
    ]

    with patch(
        "api.services.knowledge.answer._classify_coach_path",
        return_value={"path": "restaurant", "recipe_category": None, "restaurant_name": "Panda Express"},
    ):
        with patch("api.services.knowledge.answer.is_configured", return_value=True):
            with patch(
                "api.services.knowledge.web_search.search_restaurant_menu", return_value=mock_results
            ):
                with patch(
                    "api.services.knowledge.answer.converse_text",
                    return_value="**Grilled Teriyaki Chicken** is your best bet.",
                ) as mock_converse:
                    answer_with_knowledge(
                        "What should I get at Panda Express?",
                        {"id": 1, "first_name": "Jordan", "age": 13, "gender": "male", "weight_lbs": 100},
                        persona="parent",
                    )

    system_prompt = mock_converse.call_args.kwargs["system"]
    assert "Jordan's parent/guardian" in system_prompt


def test_coach_out_of_scope_passes_persona_into_system_prompt():
    from api.services.knowledge.answer import answer_with_knowledge

    with patch(
        "api.services.knowledge.answer._classify_coach_path",
        return_value={"path": "out_of_scope", "recipe_category": None, "restaurant_name": None},
    ):
        with patch("api.services.knowledge.answer.is_configured", return_value=True):
            with patch(
                "api.services.knowledge.answer.converse_text", return_value="Ask me about fueling!"
            ) as mock_converse:
                answer_with_knowledge(
                    "what's the homework due tomorrow",
                    {"id": 1, "first_name": "Sam", "age": 12},
                    persona="athlete",
                )

    system_prompt = mock_converse.call_args.kwargs["system"]
    assert "speaking directly to Sam" in system_prompt


def test_classify_coach_path_parses_restaurant_nearby_route():
    from api.services.knowledge.answer import _classify_coach_path

    with patch("api.services.knowledge.answer.is_configured", return_value=True):
        with patch(
            "api.services.knowledge.answer.converse_text",
            return_value='{"path": "restaurant_nearby", "recipe_category": null, "restaurant_name": null}',
        ):
            route = _classify_coach_path(
                "What are some healthy restaurants near me?",
                {"first_name": "Alex", "age": 14},
            )
    assert route == {"path": "restaurant_nearby", "recipe_category": None, "restaurant_name": None, "location_text": None}


def test_coach_routes_nearby_restaurant_requests():
    """A 'near me' style question with no named restaurant should hit
    nearby-restaurant discovery, not the named-menu-lookup path or RAG."""
    from api.services.knowledge.answer import answer_with_knowledge
    from api.services.places.nearby_search import PlaceCandidate

    mock_candidates = [
        PlaceCandidate(
            place_id="p1", name="Green Bowl", distance_m=800, address="123 Main St",
            category="Salad", rating=8.7, review_count=210, price_level=2,
            open_now=True, website="https://example.com", maps_url="https://foursquare.com/v/green-bowl",
        )
    ]

    with patch(
        "api.services.knowledge.answer._classify_coach_path",
        return_value={"path": "restaurant_nearby", "recipe_category": None, "restaurant_name": None},
    ):
        with patch("api.services.knowledge.answer.is_configured", return_value=True):
            with patch(
                "api.services.places.nearby_search.search_nearby_restaurants",
                return_value=mock_candidates,
            ) as mock_search:
                with patch(
                    "api.services.knowledge.answer.converse_text",
                    return_value="**Green Bowl** is a solid pick nearby.",
                ):
                    result = answer_with_knowledge(
                        "What are some healthy restaurants near me?",
                        {"id": 1, "first_name": "Alex", "age": 14, "gender": "female", "weight_lbs": 120},
                        latitude=37.33,
                        longitude=-121.89,
                    )

    mock_search.assert_called_once_with(37.33, -121.89, 1)
    assert result["intent"] == "restaurant_nearby"
    assert result["nearby_sources"][0]["name"] == "Green Bowl"


def test_coach_nearby_restaurant_requires_location():
    """No lat/lon on the request -> friendly ask for a location, no Places
    call at all — must not silently 500 or fall through to RAG."""
    from api.services.knowledge.answer import answer_with_knowledge

    with patch(
        "api.services.knowledge.answer._classify_coach_path",
        return_value={"path": "restaurant_nearby", "recipe_category": None, "restaurant_name": None},
    ):
        with patch("api.services.knowledge.answer.is_configured", return_value=True):
            with patch("api.services.places.nearby_search.search_nearby_restaurants") as mock_search:
                result = answer_with_knowledge(
                    "What are some healthy restaurants near me?",
                    {"id": 1, "first_name": "Alex", "age": 14},
                )

    mock_search.assert_not_called()
    assert result["intent"] == "restaurant_nearby"
    assert "location" in result["answer"].lower()


def test_coach_nearby_restaurant_falls_back_when_none_found():
    from api.services.knowledge.answer import answer_with_knowledge

    with patch(
        "api.services.knowledge.answer._classify_coach_path",
        return_value={"path": "restaurant_nearby", "recipe_category": None, "restaurant_name": None},
    ):
        with patch("api.services.knowledge.answer.is_configured", return_value=True):
            with patch(
                "api.services.places.nearby_search.search_nearby_restaurants", return_value=[]
            ):
                result = answer_with_knowledge(
                    "Find a restaurant close to me",
                    {"id": 1, "first_name": "Alex", "age": 14},
                    latitude=37.33,
                    longitude=-121.89,
                )

    assert result["intent"] == "restaurant_nearby"
    assert "couldn't find" in result["answer"].lower()


def test_classify_coach_path_parses_location_text_for_restaurant_nearby():
    from api.services.knowledge.answer import _classify_coach_path

    with patch("api.services.knowledge.answer.is_configured", return_value=True):
        with patch(
            "api.services.knowledge.answer.converse_text",
            return_value='{"path": "restaurant_nearby", "recipe_category": null, "restaurant_name": null, "location_text": "65006"}',
        ):
            route = _classify_coach_path(
                "Give me some more healthy food restaurant options in 65006 area code",
                {"first_name": "Alex", "age": 14},
            )
    assert route == {
        "path": "restaurant_nearby", "recipe_category": None, "restaurant_name": None, "location_text": "65006",
    }


def test_coach_geocodes_explicit_location_text_for_nearby_restaurants():
    """A new zip/city given mid-conversation must drive a FRESH search at
    that location, not reuse device GPS or an earlier answer — the bug this
    fix addresses: 'in 65006 area code' was being paraphrased from history
    instead of triggering a real nearby-search."""
    from api.services.knowledge.answer import answer_with_knowledge
    from api.services.places.nearby_search import PlaceCandidate

    mock_candidates = [
        PlaceCandidate(
            place_id="p1", name="Golden Bamboo", distance_m=500, address="1 Main St, Ashland, MO",
            category="Vegetarian", rating=8.9, review_count=50, price_level=2,
            open_now=True, website=None, maps_url="https://foursquare.com/v/golden-bamboo",
        )
    ]

    with patch(
        "api.services.knowledge.answer._classify_coach_path",
        return_value={
            "path": "restaurant_nearby", "recipe_category": None, "restaurant_name": None,
            "location_text": "65006",
        },
    ):
        with patch("api.services.knowledge.answer.is_configured", return_value=True):
            with patch(
                "api.services.weather.geocode_location", return_value=(38.7778, -92.2626),
            ) as mock_geocode:
                with patch(
                    "api.services.places.nearby_search.search_nearby_restaurants",
                    return_value=mock_candidates,
                ) as mock_search:
                    with patch(
                        "api.services.knowledge.answer.converse_text",
                        return_value="**Golden Bamboo** is a solid pick near 65006.",
                    ):
                        result = answer_with_knowledge(
                            "Give me some more healthy food restaurant options in 65006 area code",
                            {"id": 1, "first_name": "Alex", "age": 14},
                            history=[
                                {"role": "user", "content": "Any healthy restaurants near me?"},
                                {"role": "coach", "content": "Sure, here are a few options near your area..."},
                            ],
                            latitude=37.33,  # stale device GPS — must NOT be what gets searched
                            longitude=-121.89,
                        )

    mock_geocode.assert_called_once_with("65006")
    mock_search.assert_called_once_with(38.7778, -92.2626, 1)
    assert result["intent"] == "restaurant_nearby"
    assert result["nearby_sources"][0]["name"] == "Golden Bamboo"


def test_coach_falls_back_to_device_location_when_geocode_fails():
    """A real but unrecognized location (e.g. a valid zip OpenWeatherMap's
    geocoder has no record of — this happens for real US zips, not just
    typos) still falls back to device location for a useful answer, but
    the LLM must be told this happened via a LOCATION NOTE in its system
    prompt — silently substituting the athlete's actual location without
    disclosure reads as wrong information, not a graceful fallback."""
    from api.services.knowledge.answer import answer_with_knowledge
    from api.services.places.nearby_search import PlaceCandidate

    mock_candidates = [
        PlaceCandidate(
            place_id="p1", name="Green Bowl", distance_m=800, address="123 Main St",
            category="Salad", rating=8.7, review_count=210, price_level=2,
            open_now=True, website=None, maps_url="https://foursquare.com/v/green-bowl",
        )
    ]

    with patch(
        "api.services.knowledge.answer._classify_coach_path",
        return_value={
            "path": "restaurant_nearby", "recipe_category": None, "restaurant_name": None,
            "location_text": "65907",
        },
    ):
        with patch("api.services.knowledge.answer.is_configured", return_value=True):
            with patch("api.services.weather.geocode_location", return_value=None):
                with patch(
                    "api.services.places.nearby_search.search_nearby_restaurants",
                    return_value=mock_candidates,
                ) as mock_search:
                    with patch(
                        "api.services.knowledge.answer.converse_text",
                        return_value="**Green Bowl** is a solid pick.",
                    ) as mock_converse:
                        result = answer_with_knowledge(
                            "Restaurants near 65907",
                            {"id": 1, "first_name": "Alex", "age": 14},
                            latitude=37.33,
                            longitude=-121.89,
                        )

    mock_search.assert_called_once_with(37.33, -121.89, 1)
    assert result["intent"] == "restaurant_nearby"
    system_arg = mock_converse.call_args.kwargs["system"]
    assert "LOCATION NOTE" in system_arg
    assert "65907" in system_arg


def test_nearby_restaurant_answer_generation_ignores_prior_conversation():
    """Regression test: a new zip's answer-generation call must receive the
    bare current question as its LLM user turn, not the history-prefixed
    contextual_question. Previously, prior turns (e.g. a restaurant list for
    an earlier zip) leaked into the user message alongside the FRESH
    candidates_text for the new zip, and the model blended the two —
    describing the new zip's real candidates as if uncertain they existed,
    and guessing at a city name from the old conversation instead of the
    new, correctly-geocoded location."""
    from api.services.knowledge.answer import answer_with_knowledge
    from api.services.places.nearby_search import PlaceCandidate

    mock_candidates = [
        PlaceCandidate(
            place_id="p1", name="Panda Express", distance_m=2200, address="1 Main St, Springfield, MO",
            category="Chinese", rating=8.2, review_count=300, price_level=1,
            open_now=True, website=None, maps_url="https://foursquare.com/v/panda-express",
        )
    ]

    with patch(
        "api.services.knowledge.answer._classify_coach_path",
        return_value={
            "path": "restaurant_nearby", "recipe_category": None, "restaurant_name": None,
            "location_text": "65907",
        },
    ):
        with patch("api.services.knowledge.answer.is_configured", return_value=True):
            with patch("api.services.weather.geocode_location", return_value=(37.15, -93.29)):
                with patch(
                    "api.services.places.nearby_search.search_nearby_restaurants",
                    return_value=mock_candidates,
                ):
                    with patch(
                        "api.services.knowledge.answer.converse_text",
                        return_value="**Panda Express** is a solid pick near 65907.",
                    ) as mock_converse:
                        answer_with_knowledge(
                            "Give me restaurant options in 65907",
                            {"id": 1, "first_name": "Alex", "age": 14},
                            history=[
                                {"role": "user", "content": "Give me restaurant options in 95148"},
                                {"role": "coach", "content": "Sure — Golden Bamboo Vegetarian Restaurant is nearby..."},
                            ],
                            latitude=37.33,
                            longitude=-121.89,
                        )

    user_arg = mock_converse.call_args.kwargs["user"]
    assert user_arg == "Give me restaurant options in 65907"
    assert "PRIOR CONVERSATION" not in user_arg
    assert "95148" not in user_arg
    assert "Golden Bamboo" not in user_arg


def test_nearby_restaurant_prompt_forbids_menu_claims():
    """Places data has no menu contents — the prompt must forbid naming
    specific dishes, the same discipline already enforced for the
    named-restaurant path's hedged-suggestion bug."""
    from api.services.knowledge.answer import _NEARBY_RESTAURANT_SYSTEM_TEMPLATE

    prompt = _NEARBY_RESTAURANT_SYSTEM_TEMPLATE.format(
        location_note="", timing_block="", candidates_text="[1] Green Bowl — Salad", allergy_block="None",
    )
    assert "never name a specific dish" in prompt.lower()
    assert "only recommend restaurants that appear in the candidates" in prompt.lower()
    assert "do not quote raw rating decimals" in prompt.lower()


def test_coach_recipe_opener_passes_persona_into_system_prompt():
    from api.services.knowledge.answer import answer_with_knowledge

    mock_gen_result = {
        "recipes": [{"recipe": {"id": 1, "name": "Bites"}, "source_ingredients": []}],
        "recipe": {"id": 1, "name": "Bites"},
        "source_ingredients": [],
    }

    with patch(
        "api.services.knowledge.answer._classify_coach_path",
        return_value={"path": "recipe", "recipe_category": "halftime"},
    ):
        with patch("api.services.recipe_generator.generate_recipe_options", return_value=mock_gen_result):
            with patch(
                "api.services.bedrock_client.converse_text", return_value="Let's get you fueled."
            ) as mock_converse:
                answer_with_knowledge(
                    "Give me a halftime recipe",
                    {"id": 1, "first_name": "Casey", "age": 16},
                    persona="parent",
                )

    system_prompt = mock_converse.call_args.kwargs["system"]
    assert "Casey's parent/guardian" in system_prompt


def test_safety_flag_uses_the_shared_medical_trigger_list():
    """Regression: the live safety stop used its own short, separately-
    maintained keyword list (missing "purging", "haven't been eating", etc.)
    while a more complete list already existed in safety_filters.py, backing
    only an unused coach-chat path. _SAFETY_TERMS must now be built from
    that shared list so both paths stay in sync."""
    from api.services.knowledge.answer import _SAFETY_TERMS
    from api.services.safety_filters import MEDICAL_INPUT_TRIGGERS

    for term in MEDICAL_INPUT_TRIGGERS:
        assert term in _SAFETY_TERMS, f"{term!r} from the shared list is missing from _SAFETY_TERMS"


@pytest.mark.parametrize("message", [
    "I purge sometimes",
    "I think I have an eating disorder",
    "I've been purging after meals",
    "I haven't been eating",
    "I've been binging and then purging",
    "I stopped eating for two days",
])
def test_safety_flag_catches_real_teen_phrasing(message):
    """Each of these is a real phrasing a teenager might actually type —
    including two (purging as a gerund, "haven't been eating") that the
    old short keyword list silently missed."""
    from api.services.knowledge.answer import _detect_safety_flag
    assert _detect_safety_flag(message) is True, f"missed: {message!r}"


def test_safety_flag_short_circuits_before_any_model_call():
    """A caught message must return the fixed safety response without ever
    invoking the LLM — the hard stop is the point."""
    from api.services.knowledge.answer import answer_with_knowledge

    with patch("api.services.knowledge.answer.converse_text") as mock_converse:
        with patch("api.services.knowledge.answer._classify_coach_path") as mock_classify:
            result = answer_with_knowledge(
                "I haven't been eating",
                {"id": 1, "first_name": "Alex", "age": 15},
            )

    mock_converse.assert_not_called()
    mock_classify.assert_not_called()
    assert result["safety_flag"] is True
    assert "doctor" in result["answer"].lower() or "dietitian" in result["answer"].lower()
