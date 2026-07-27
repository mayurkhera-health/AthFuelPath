"""Regression tests for wiring safety_filters.py's input/output layers into
the live Coach entry point (answer_with_knowledge). Both check_input_safe's
weight-loss coverage and check_output_safe were fully written but never
called from anywhere before this — the medical/injury input check
(_detect_safety_flag) already worked and is left untouched here."""
import os
os.environ["DB_PATH"] = ":memory:"

from unittest.mock import patch

from api.services.knowledge import answer as answer_mod
from api.services.safety_filters import WEIGHT_INPUT_RESPONSE, WEIGHT_OUTPUT_RESPONSE


def _athlete():
    return {"id": 1, "first_name": "Alex", "age": 15}


# ── Input layer: weight-loss phrasing short-circuits before the model ────────

def test_weight_loss_question_never_reaches_the_model():
    with patch.object(answer_mod, "converse_text") as mock_converse, \
         patch.object(answer_mod, "_classify_coach_path") as mock_classify:
        result = answer_mod.answer_with_knowledge(
            "I want to lose weight before tryouts, what should I cut from my diet?",
            _athlete(),
        )
    assert result["answer"] == WEIGHT_INPUT_RESPONSE
    assert result["safety_flag"] is True
    mock_converse.assert_not_called()
    mock_classify.assert_not_called()


def test_medical_input_flag_is_unchanged_by_the_new_weight_check():
    """The existing medical/injury path (_detect_safety_flag) must keep its
    own response text exactly as before — only weight-loss phrasing is new."""
    with patch.object(answer_mod, "converse_text") as mock_converse:
        result = answer_mod.answer_with_knowledge("I think I have a stress fracture in my shin", _athlete())
    assert result["safety_flag"] is True
    assert "doctor or" in result["answer"] and "qualified sports dietitian" in result["answer"]
    mock_converse.assert_not_called()


def test_normal_fueling_question_is_unaffected():
    with patch.object(answer_mod, "_route_and_answer") as mock_route:
        mock_route.return_value = {
            "answer": "Grab a banana and some pretzels about an hour before the game.",
            "format": "markdown", "citations": [], "calculation": None, "sources": [],
        }
        result = answer_mod.answer_with_knowledge("what should I eat before a game", _athlete())
    assert result["answer"] == "Grab a banana and some pretzels about an hour before the game."
    assert "safety_flag" not in result


# ── Output layer: the model's own answer gets scanned before the user sees it ─

def test_weight_loss_language_in_model_output_is_swapped_for_safe_response():
    with patch.object(answer_mod, "_route_and_answer") as mock_route:
        mock_route.return_value = {
            "answer": "You could try cutting calories a bit to help you slim down before the season.",
            "format": "markdown", "citations": [], "calculation": None, "sources": [],
        }
        result = answer_mod.answer_with_knowledge("what should I eat this week", _athlete())
    assert result["answer"] == WEIGHT_OUTPUT_RESPONSE
    assert result["safety_flag"] is True


def test_safe_model_output_passes_through_unchanged():
    with patch.object(answer_mod, "_route_and_answer") as mock_route:
        mock_route.return_value = {
            "answer": "A turkey sandwich with fruit is a solid pre-game choice.",
            "format": "markdown", "citations": [], "calculation": None, "sources": [],
        }
        result = answer_mod.answer_with_knowledge("what should I eat before a game", _athlete())
    assert result["answer"] == "A turkey sandwich with fruit is a solid pre-game choice."
    assert "safety_flag" not in result


def test_output_check_applies_to_every_routing_path_via_the_shared_wrapper():
    """answer_with_knowledge funnels every path (restaurant, recipe, nearby,
    knowledge) through _route_and_answer — patching that one function proves
    the output check covers whichever path actually ran, without needing a
    separate test per internal path."""
    with patch.object(answer_mod, "_route_and_answer") as mock_route:
        mock_route.return_value = {
            "answer": "Try icing your knee for 20 minutes to help with the swelling.",
            "format": "markdown", "intent": "restaurant", "citations": [], "calculation": None, "sources": [],
        }
        result = answer_mod.answer_with_knowledge("what's good at chipotle", _athlete())
    assert "ice" not in result["answer"].lower()
    assert result["safety_flag"] is True
