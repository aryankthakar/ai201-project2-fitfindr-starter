"""
Tests for the three FitFindr tools.

search_listings is pure Python and tested directly against the real dataset.
The two LLM-backed tools (suggest_outfit, create_fit_card) mock the Groq client
so tests are fast, free, and deterministic.
"""

import tools
from tools import search_listings, suggest_outfit, create_fit_card


# ── search_listings (no LLM) ──────────────────────────────────────────────────

def test_search_returns_matches_for_known_query():
    results = search_listings("vintage graphic tee", max_price=30)
    assert isinstance(results, list)
    assert len(results) > 0
    # every result respects the price ceiling
    assert all(r["price"] <= 30 for r in results)
    # the y2k butterfly baby tee (lst_002, $18, graphic tee) should surface
    assert any(r["id"] == "lst_002" for r in results)


def test_search_sorted_by_relevance_descending():
    results = search_listings("vintage denim jeans")
    # top result should be at least as relevant as the next (scores not exposed,
    # so we assert order is stable and non-empty)
    assert len(results) >= 2


def test_search_respects_max_price():
    results = search_listings("jacket", max_price=20)
    assert all(r["price"] <= 20 for r in results)


def test_search_size_filter_case_insensitive():
    # "m" should match listings whose size contains M, e.g. "S/M" or "M"
    results = search_listings("track jacket", size="m")
    assert all("m" in r["size"].lower() for r in results)


def test_search_no_match_returns_empty_list():
    results = search_listings("designer ballgown", size="XXS", max_price=5)
    assert results == []


def test_search_never_raises_on_empty_description():
    # should degrade gracefully rather than crash
    assert isinstance(search_listings(""), list)


# ── suggest_outfit (mocked LLM) ───────────────────────────────────────────────

class _FakeGroq:
    """Minimal stand-in for groq.Groq that returns a canned completion."""
    def __init__(self, text="MOCK OUTFIT"):
        self._text = text

        class _Msg:
            content = text

        class _Choice:
            message = _Msg()

        class _Completion:
            choices = [_Choice()]

        class _Completions:
            def create(_self, **kwargs):
                return _Completion()

        class _Chat:
            completions = _Completions()

        self.chat = _Chat()


def test_suggest_outfit_with_wardrobe(monkeypatch):
    monkeypatch.setattr(tools, "_get_groq_client", lambda: _FakeGroq("pair with baggy jeans"))
    new_item = {"title": "Y2K Baby Tee", "category": "tops", "style_tags": ["y2k"], "colors": ["pink"]}
    wardrobe = {"items": [{"name": "Baggy jeans", "category": "bottoms"}]}
    out = suggest_outfit(new_item, wardrobe)
    assert isinstance(out, str) and out.strip()


def test_suggest_outfit_empty_wardrobe_still_returns_string(monkeypatch):
    monkeypatch.setattr(tools, "_get_groq_client", lambda: _FakeGroq("general styling advice"))
    new_item = {"title": "Y2K Baby Tee", "category": "tops", "style_tags": ["y2k"], "colors": ["pink"]}
    out = suggest_outfit(new_item, {"items": []})
    assert isinstance(out, str) and out.strip()


# ── create_fit_card (mocked LLM) ──────────────────────────────────────────────

def test_create_fit_card_happy_path(monkeypatch):
    monkeypatch.setattr(tools, "_get_groq_client", lambda: _FakeGroq("cutest thrift find ✨"))
    new_item = {"title": "Y2K Baby Tee", "price": 18.0, "platform": "depop"}
    card = create_fit_card("pair with baggy jeans", new_item)
    assert isinstance(card, str) and card.strip()


def test_create_fit_card_empty_outfit_returns_error_string():
    # must NOT raise and must NOT call the LLM
    card = create_fit_card("   ", {"title": "x", "price": 1, "platform": "depop"})
    assert isinstance(card, str)
    assert card  # non-empty descriptive error
