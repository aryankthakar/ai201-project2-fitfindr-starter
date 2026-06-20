"""
agent.py

The FitFindr planning loop. Orchestrates the three tools in response to a
natural language user query, passing state between them via a session dict.

Complete tools.py and test each tool in isolation before implementing this file.

Usage (once implemented):
    from agent import run_agent
    from utils.data_loader import get_example_wardrobe

    result = run_agent(
        query="vintage graphic tee under $30, size M",
        wardrobe=get_example_wardrobe(),
    )
    print(result["fit_card"])
    print(result["error"])   # None on success
"""

import re

from tools import search_listings, suggest_outfit, create_fit_card


# ── query parsing ─────────────────────────────────────────────────────────────

# Common clothing-size tokens we recognize in free-text queries.
_SIZE_WORDS = ["xxs", "xs", "s", "m", "l", "xl", "xxl"]


def _parse_query(query: str) -> dict:
    """
    Extract a description, optional size, and optional max_price from a free-text
    query using regex/string parsing (deterministic, no LLM call).

    Returns a dict: {"description": str, "size": str|None, "max_price": float|None}
    """
    text = query or ""
    leftover = text

    # max_price: "$30", "under 30", "below $40"
    max_price = None
    price_match = re.search(r"\$?\s*(\d+(?:\.\d+)?)", text)
    if re.search(r"(under|below|less than|max|<)\s*\$?\s*\d", text, re.I) or "$" in text:
        if price_match:
            max_price = float(price_match.group(1))
            leftover = leftover.replace(price_match.group(0), " ")

    # size: "size M" or a standalone size token
    size = None
    size_match = re.search(r"size\s+([a-zA-Z0-9/]+)", text, re.I)
    if size_match:
        size = size_match.group(1).upper()
        leftover = leftover.replace(size_match.group(0), " ")
    else:
        for tok in re.findall(r"[a-zA-Z]+", leftover):
            if tok.lower() in _SIZE_WORDS and len(tok) <= 3:
                size = tok.upper()
                break

    # description: whatever remains, cleaned up
    description = re.sub(r"(under|below|less than|max)\b", " ", leftover, flags=re.I)
    description = re.sub(r"\s+", " ", description).strip()

    return {"description": description, "size": size, "max_price": max_price}


# ── session state ─────────────────────────────────────────────────────────────

def _new_session(query: str, wardrobe: dict) -> dict:
    """
    Initialize and return a fresh session dict for one user interaction.

    The session dict is the single source of truth for everything that happens
    during a run — it stores the original query, parsed parameters, tool results,
    and any error that caused early termination.

    You may add fields to this dict as needed for your implementation.
    """
    return {
        "query": query,              # original user query
        "parsed": {},                # extracted description / size / max_price
        "search_results": [],        # list of matching listing dicts
        "selected_item": None,       # top result, passed into suggest_outfit
        "wardrobe": wardrobe,        # user's wardrobe dict
        "outfit_suggestion": None,   # string returned by suggest_outfit
        "fit_card": None,            # string returned by create_fit_card
        "error": None,               # set if the interaction ended early
    }


# ── planning loop ─────────────────────────────────────────────────────────────

def run_agent(query: str, wardrobe: dict) -> dict:
    """
    Main agent entry point. Runs the FitFindr planning loop for a single
    user interaction and returns the completed session dict.

    Args:
        query:    Natural language user request
                  (e.g., "vintage graphic tee under $30, size M")
        wardrobe: User's wardrobe dict — use get_example_wardrobe() or
                  get_empty_wardrobe() from utils/data_loader.py

    Returns:
        The session dict after the interaction completes. Check session["error"]
        first — if it is not None, the interaction ended early and the other
        output fields (outfit_suggestion, fit_card) will be None.

    TODO — implement this function using the planning loop you designed in planning.md:

        Step 1: Initialize the session with _new_session().

        Step 2: Parse the user's query to extract a description, size, and
                max_price. You can use regex, string splitting, or ask the LLM
                to parse it — document your choice in planning.md.
                Store the result in session["parsed"].

        Step 3: Call search_listings() with the parsed parameters.
                Store results in session["search_results"].
                If no results: set session["error"] to a helpful message and
                return the session early. Do NOT proceed to suggest_outfit
                with empty input.

        Step 4: Select the item to use (e.g., the top result).
                Store it in session["selected_item"].

        Step 5: Call suggest_outfit() with the selected item and wardrobe.
                Store the result in session["outfit_suggestion"].

        Step 6: Call create_fit_card() with the outfit suggestion and selected item.
                Store the result in session["fit_card"].

        Step 7: Return the session.

    Before writing code, complete the Planning Loop and State Management sections
    of planning.md — your implementation should match what you described there.
    """
    session = _new_session(query, wardrobe)

    # Step 2: parse the query into search constraints.
    session["parsed"] = _parse_query(query)

    # Step 3: search listings.
    session["search_results"] = search_listings(
        description=session["parsed"]["description"],
        size=session["parsed"]["size"],
        max_price=session["parsed"]["max_price"],
    )
    if not session["search_results"]:
        session["error"] = (
            "No matching items found. Try adjusting the description, size, or price."
        )
        return session

    # Step 4: select the top-ranked result.
    session["selected_item"] = session["search_results"][0]

    # Steps 5-6: LLM-backed styling. Guard against API/network failures so the
    # loop degrades into a clean error rather than crashing the caller (UI/CLI).
    try:
        session["outfit_suggestion"] = suggest_outfit(
            session["selected_item"], session["wardrobe"]
        )
        session["fit_card"] = create_fit_card(
            session["outfit_suggestion"], session["selected_item"]
        )
    except Exception as exc:  # noqa: BLE001 — surface any tool/API error to the user
        session["outfit_suggestion"] = None
        session["fit_card"] = None
        session["error"] = (
            f"Found a listing, but couldn't generate styling right now: {exc}"
        )

    # Step 7: done.
    return session


# ── CLI test ──────────────────────────────────────────────────────────────────

def _print_trace(session: dict) -> None:
    """Print one run as separated tool-call steps so state passing is visible."""
    bar = "─" * 70

    print(bar)
    print("STEP 1 — parse query")
    print(bar)
    print(f"  query   : {session['query']}")
    print(f"  parsed  : {session['parsed']}")

    print(f"\n{bar}")
    print("STEP 2 — search_listings(description, size, max_price)")
    print(bar)
    print(f"  returned {len(session['search_results'])} listing(s), ranked by relevance")
    for i, item in enumerate(session["search_results"][:3]):
        print(f"    {i}: {item['title']} — ${item['price']:.0f} ({item['platform']})")
    if session["error"] and not session["selected_item"]:
        print(f"\n  >> EMPTY RESULT — stopping early")
        print(f"  >> error: {session['error']}")
        return

    print(f"\n{bar}")
    print("STEP 3 — select top result  (search output -> suggest_outfit input)")
    print(bar)
    print(f"  selected_item: {session['selected_item']['title']}")

    print(f"\n{bar}")
    print("STEP 4 — suggest_outfit(selected_item, wardrobe)")
    print(bar)
    if session["error"]:
        print(f"  >> error: {session['error']}")
        return
    print(f"  outfit_suggestion:\n    {session['outfit_suggestion']}")

    print(f"\n{bar}")
    print("STEP 5 — create_fit_card(outfit_suggestion, selected_item)")
    print(bar)
    print(f"  fit_card:\n    {session['fit_card']}")


if __name__ == "__main__":
    from utils.data_loader import get_example_wardrobe, get_empty_wardrobe

    print("\n############ HAPPY PATH ############\n")
    _print_trace(run_agent(
        query="looking for a vintage graphic tee under $30",
        wardrobe=get_example_wardrobe(),
    ))

    print("\n\n############ NO-RESULTS PATH ############\n")
    _print_trace(run_agent(
        query="designer ballgown size XXS under $5",
        wardrobe=get_example_wardrobe(),
    ))
