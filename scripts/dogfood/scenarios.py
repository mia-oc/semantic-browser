"""Scenario definitions for the dogfood harness.

A scenario is a goal + an *oracle script* (what a competent model would choose, expressed
as label regexes) + an independent success check on real page state.

The oracle only picks among actions the model was actually **shown** (see runner), so a
browser layer that hides or mislabels its options is penalised exactly as it would be
with a real model.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Step:
    match: list[str]  # label regexes, tried in order (most specific first)
    op: str | None = None  # restrict to op family: fill|click|open|select
    value: str | None = None  # text to type for fill
    nth: int | None = None  # fallback: nth action of this op (0-based) if no regex matches
    hover: bool = False
    optional: bool = False  # e.g. a consent banner that only some visitors get


@dataclass
class Scenario:
    name: str
    category: str
    url: str  # relative to fixture base, or absolute
    goal: str
    steps: list[Step]
    # Independent success check (any of these matching => success)
    ok_title: str | None = None
    ok_url: str | None = None
    ok_text: str | None = None
    # Must appear in text shown to the model at some point (content-visibility check)
    must_see: str | None = None
    net: bool = False  # needs internet
    headful_only: bool = False
    tags: list[str] = field(default_factory=list)


LOCAL: list[Scenario] = [
    Scenario(
        "shop_duplicates", "context", "/shop", "Add the Blue Mug to the basket.",
        [Step(["Add to basket.*Blue Mug", "Blue Mug"], op="click", nth=3)],
        ok_title=r"^basket:Blue Mug$", tags=["duplicates"],
    ),
    Scenario(
        "cookie_overlay", "blockers", "/cookie", "Dismiss cookies then open the Pricing page.",
        [Step(["Accept all"], op="click"), Step(["^Pricing$"], op="open")],
        ok_title=r"^Pricing$", tags=["overlay"],
    ),
    Scenario(
        "shadow_login", "web-components", "/shadow", "Log in as user 'matt'.",
        [Step(["Username"], op="fill", value="matt"), Step(["Password"], op="fill", value="hunter2"),
         Step(["Sign in"], op="click")],
        ok_title=r"^welcome:matt$", tags=["shadow-dom"],
    ),
    Scenario(
        "iframe_payment", "frames", "/iframe", "Pay with card 4242.",
        [Step(["Card number"], op="fill", value="4242"), Step(["Pay now"], op="click")],
        ok_title=r"^paid:4242$", tags=["cross-origin-iframe"],
    ),
    Scenario(
        "custom_dropdown_date", "widgets", "/dropdown", "Search trips to Paris on the 17th.",
        [Step(["Destination|Choose"], op="click"), Step(["^Paris$"], op="click"),
         Step(["^17$"], op="click"), Step(["Search trips"], op="click")],
        ok_title=r"^trip:Paris:17$", tags=["custom-widgets", "div-click"],
    ),
    Scenario(
        "spa_settings", "spa", "/spa/home", "Open Settings, set display name to Zed and save.",
        [Step(["^Settings$"], op="open"), Step(["Display name"], op="fill", value="Zed"),
         Step(["Save settings"], op="click")],
        ok_title=r"^saved:Zed$", tags=["spa", "delayed-render"],
    ),
    Scenario(
        "search_read_price", "reading", "/search", "Find the price of Anvil Mini and open it.",
        [Step(["Search catalogue"], op="fill", value="anvil"), Step(["Anvil Mini"], op="open")],
        ok_title=r"^item-opened$", must_see=r"24\.99", tags=["js-rendered", "content"],
    ),
    Scenario(
        "lazy_feed_item35", "scroll", "/lazy", "Open item 35 from the feed.",
        [Step(["Open item 35"], op="click")],
        ok_title=r"^opened:35$", tags=["lazy-load", "scroll"],
    ),
    Scenario(
        "hover_menu", "widgets", "/hover", "Open the Anvils page from the Products menu.",
        [Step(["Products"], op="click", hover=True), Step(["^Anvils$"], op="open")],
        ok_title=r"^anvils-page$", tags=["hover"],
    ),
]


# Real public sites. READ-ONLY: searches and navigation only, never logins, purchases or submissions.
REAL: list[Scenario] = [
    Scenario(
        "wikipedia_search", "reading", "https://en.wikipedia.org/wiki/Main_Page", "Search Wikipedia for Alan Turing.",
        [Step(["Search Wikipedia"], op="fill", value="Alan Turing")],
        ok_url=r"Alan_Turing", must_see=r"Turing", net=True, tags=["real", "search"],
    ),
    Scenario(
        "hn_comments", "lists", "https://news.ycombinator.com/", "Open the comments of the first story.",
        [Step([r"^\d+\s+comments?$"], op="open", nth=0)],
        ok_url=r"item\?id=", net=True, tags=["real", "dense-list"],
    ),
    Scenario(
        "govuk_search", "forms", "https://www.gov.uk/", "Search GOV.UK for passport.",
        [Step(["^Accept additional cookies"], op="click", optional=True),
         Step(["Search GOV.UK", "^Search"], op="fill", value="passport")],
        ok_url=r"search/all\?keywords=passport|passport", net=True, tags=["real", "search"],
    ),
    Scenario(
        "github_issues", "navigation", "https://github.com/microsoft/playwright", "Open the Issues tab.",
        [Step([r"^Issues\b"], op="open")],
        ok_url=r"/issues", net=True, tags=["real", "spa-ish"],
    ),
    Scenario(
        "bbc_sport_football", "overlay", "https://www.bbc.co.uk/sport", "Dismiss consent if shown, open Football.",
        [Step(["^Yes, I agree", "^I agree", "^Accept"], op="click", optional=True), Step([r"^Football\b"], op="open")],
        ok_url=r"/sport/football", net=True, tags=["real", "consent"],
    ),
    Scenario(
        "ddg_search", "forms", "https://duckduckgo.com/", "Search DuckDuckGo for semantic browser.",
        [Step(["Search with DuckDuckGo", "^Search"], op="fill", value="semantic browser")],
        ok_url=r"q=semantic", net=True, tags=["real", "search", "bot-defence"],
    ),
    Scenario(
        "nhs_search", "forms", "https://www.nhs.uk/", "Search NHS for asthma.",
        [Step(["^Accept"], op="click", optional=True), Step(["Search"], op="fill", value="asthma")],
        ok_url=r"asthma", net=True, tags=["real", "search"],
    ),
    Scenario(
        "amazon_search", "hard", "https://www.amazon.co.uk/", "Search Amazon for usb cable (read-only).",
        [Step(["^Accept$", "Accept cookies"], op="click", optional=True),
         Step(["Search Amazon", "Search"], op="fill", value="usb cable")],
        ok_url=r"[?&]k=usb", net=True, tags=["real", "hard", "bot-defence"],
    ),
]


def by_name(names: list[str] | None, which: str = "local") -> list[Scenario]:
    allsc = {"local": LOCAL, "real": REAL, "all": LOCAL + REAL}[which]
    if not names:
        return allsc
    wanted = set(names)
    return [s for s in allsc if s.name in wanted or any(t in wanted for t in s.tags)]
