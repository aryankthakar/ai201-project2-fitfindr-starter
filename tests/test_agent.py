"""
Tests for the planning loop, query parser, and state management in agent.py.

search_listings runs for real (pure Python). The two LLM-backed tools are
monkeypatched so the loop is exercised without hitting the Groq API.
"""

import agent
from agent import run_agent, _parse_query
from utils.data_loader import get_example_wardrobe, get_empty_wardrobe


# ── query parser ──────────────────────────────────────────────────────────────

def test_parse_extracts_price():
    p = _parse_query("vintage graphic tee under $30")
    assert p["max_price"] == 30.0
    assert "30" not in p["description"]
    assert "vintage" in p["description"]


def test_parse_extracts_size():
    p = _parse_query("90s track jacket in size M")
    assert p["size"] == "M"


def test_parse_no_constraints():
    p = _parse_query("flowy midi skirt")
    assert p["max_price"] is None
    assert p["size"] is None
    assert "skirt" in p["description"]


# ── planning loop (LLM tools mocked) ──────────────────────────────────────────

def _mock_llm_tools(monkeypatch):
    monkeypatch.setattr(agent, "suggest_outfit", lambda item, wardrobe: "MOCK OUTFIT")
    monkeypatch.setattr(agent, "create_fit_card", lambda outfit, item: "MOCK FIT CARD")


def test_happy_path_populates_state(monkeypatch):
    _mock_llm_tools(monkeypatch)
    s = run_agent("vintage graphic tee under $30", get_example_wardrobe())
    assert s["error"] is None
    assert s["selected_item"] is not None
    assert s["selected_item"]["price"] <= 30
    assert s["outfit_suggestion"] == "MOCK OUTFIT"
    assert s["fit_card"] == "MOCK FIT CARD"


def test_no_results_sets_error_and_stops_early(monkeypatch):
    _mock_llm_tools(monkeypatch)
    s = run_agent("designer ballgown size XXS under $5", get_example_wardrobe())
    assert s["error"] is not None
    assert s["outfit_suggestion"] is None
    assert s["fit_card"] is None


def test_llm_failure_degrades_gracefully(monkeypatch):
    def _boom(*args, **kwargs):
        raise RuntimeError("API down")

    monkeypatch.setattr(agent, "suggest_outfit", _boom)
    monkeypatch.setattr(agent, "create_fit_card", lambda outfit, item: "unused")
    s = run_agent("vintage graphic tee under $30", get_example_wardrobe())
    assert s["error"] is not None
    assert s["selected_item"] is not None  # search succeeded before the failure
    assert s["fit_card"] is None


def test_empty_wardrobe_still_succeeds(monkeypatch):
    _mock_llm_tools(monkeypatch)
    s = run_agent("vintage graphic tee under $30", get_empty_wardrobe())
    assert s["error"] is None
    assert s["fit_card"] == "MOCK FIT CARD"
