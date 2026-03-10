# Vision: Semantic Browser Runtime

## North Star

**Make the web look like a structured tool API for LLMs.**

The Semantic Browser Runtime turns a live browser session into a stable,
compact, semantically meaningful action surface that any external planner
can reason over safely and cheaply — without raw DOM sludge, brittle
selectors, giant blobs of irrelevant state, or screenshots with no
grounding.

Think BBC Micro text-adventure mode for the modern web: pure actions,
relevant context, zero bloat.

---

## The Problem

Modern LLMs are good at choosing the next step in a task. They are given
dreadful browser context:

| What LLMs get today              | What they need                          |
|----------------------------------|-----------------------------------------|
| Raw DOM dumps                    | Structured semantic regions             |
| Screenshots with no grounding    | Named actions with stable IDs           |
| Brittle CSS/XPath selectors      | Deterministic locator recipes           |
| Giant pages re-sent every turn   | Compact deltas between steps            |
| No concept of "what can I do?"   | Validated executable action surfaces    |
| No concept of "what's blocking?" | Explicit blocker and unreliability flags |

This library is the compiler that bridges that gap.

---

## What This Is

A **website-to-action-surface compiler**.

It observes a rendered page and compiles it into a structured model that
an external planner can reason over safely and cheaply.

## What This Is Not

- Not a new browser engine
- Not a headless crawler
- Not a local autonomous agent
- Not a visual-only browser tool
- Not a CAPTCHA solver
- Not a universal answer to every awful website on earth

---

## Non-Negotiables

1. **Deterministic first** — the core extraction works without any local
   LLM. Heuristic-driven, standards-aware, browser-grounded.

2. **External planner only** — the runtime never chooses the next user
   action. It classifies, ranks, and surfaces. The caller decides.

3. **Honest failure over fake confidence** — if a page is too hostile,
   too unstable, or too semantically broken, the runtime fails explicitly
   and says why. That is correct behaviour.

4. **Token economy is a first-class feature** — deltas by default, rich
   observations only when needed. The caller should not re-read the
   entire page every turn.

5. **Two clean operating modes** — managed (batteries-included) and
   attached (bring your own browser). Both are first-class citizens.

6. **Three clean interfaces** — Python library, optional local service,
   CLI. All backed by the same core.

7. **Standards-first extraction** — HTML semantics, ARIA, labels, form
   associations, landmarks, accessible names. Not CSS hacks.

8. **Stable IDs** — elements, regions, actions, and content items must
   survive ordinary re-renders without flapping.

9. **Serious web focus** — optimise for high-traffic consumer sites,
   forms, search, retail, travel, dashboards, SaaS, docs. Do not
   optimise for garbage sites, ad mazes, or semantically broken pages.

10. **No local model required** — optional LLM hooks may come later, but
    the MVP must never depend on one.

---

## Target Users

| User                        | How they use it                              |
|-----------------------------|----------------------------------------------|
| Claude Code / Codex / Cursor| Local service or MCP adapter                 |
| Custom AI agent builders    | Python library embedded in orchestration     |
| Tool-calling runtimes       | HTTP/WebSocket JSON API                      |
| Engineers debugging agents  | CLI for observation, inspection, trace export |

---

## Success Looks Like

A developer installs `semantic-browser[managed]`, launches a session,
points it at a serious website, calls `observe()`, and gets back a
compact structured model that tells them:

- What page they're on
- What regions exist
- What forms are present and their state
- What content groups are visible
- What actions are available
- What's blocking them
- How confident the extraction is

They call `act()` with an action ID, and get back a delta showing exactly
what changed — not the entire page again.

The whole round-trip is token-cheap, deterministic, and reliable.

---

## Failure Looks Like

- The tool mostly emits raw DOM disguised as structure
- Actions are not reliably executable
- Stable IDs flap constantly
- Attached mode is awkward or brittle
- Managed mode is painful to bootstrap
- The runtime requires a local model to work
- There is no proper delta mode
- It cannot distinguish a good page from a semantically poor one
