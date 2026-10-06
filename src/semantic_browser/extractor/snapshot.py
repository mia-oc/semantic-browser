"""v2 snapshot capture: one JS walk per frame, merged into a single page snapshot with short global refs."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from importlib import resources
from typing import Any

_JS_CACHE: str | None = None

# JS that resolves a ref back to the exact live element (used by the executor).
RESOLVE_JS = """(id) => { const r = window.__sb; if (!r) return null; const w = r.els.get(id); const el = w && w.deref();
  return (el && el.isConnected) ? el : null; }"""


def snapshot_js() -> str:
    global _JS_CACHE
    if _JS_CACHE is None:
        _JS_CACHE = resources.files("semantic_browser.extractor").joinpath("snapshot.js").read_text(encoding="utf-8")
    return _JS_CACHE


@dataclass
class RefEntry:
    ref: int
    frame: Any
    local: int
    gen: str
    fingerprint: str
    kind: str
    op: str
    name: str
    ctx: str = ""
    click_proxy: int = 0


@dataclass
class RefTable:
    """Maps short model-facing refs <-> live elements (frame, local id)."""

    next_ref: int = 1
    main_gen: str = ""
    by_key: dict[tuple[int, str, int], int] = field(default_factory=dict)
    by_fp: dict[str, int] = field(default_factory=dict)
    entries: dict[int, RefEntry] = field(default_factory=dict)

    def reset(self, gen: str = "") -> None:
        """New document: forget every element but keep counting, so a number from an earlier page can never be
        silently re-used for a different element (an old `click 3` must fail, not hit the new page's [3])."""
        self.main_gen = gen
        self.by_key.clear()
        self.by_fp.clear()
        self.entries.clear()

    def get(self, ref: int | str) -> RefEntry | None:
        try:
            return self.entries.get(int(str(ref).lstrip("eE#[").rstrip("]")))
        except (TypeError, ValueError):
            return None


@dataclass
class PageSnapshot:
    title: str
    url: str
    ready: str
    gen: str
    scroll: dict[str, float]
    nodes: list[dict[str, Any]]
    flow: list[list[Any]]
    layer: dict[str, Any] | None
    frame_count: int
    stats: dict[str, Any]
    truncated: bool = False


def _fingerprint(node: dict[str, Any]) -> str:
    return "|".join(
        [str(node.get("frame_id", "main")), str(node.get("op", "")), str(node.get("kind", "")),
         str(node.get("name", ""))[:60], str(node.get("ctx", ""))[:40], str(node.get("href", ""))[:80]]
    )


async def _eval_frame(frame: Any, opts: dict[str, Any], attempts: int = 3) -> dict[str, Any]:
    last: Exception | None = None
    for i in range(attempts):
        try:
            raw = await frame.evaluate(snapshot_js(), opts)
            return json.loads(raw) if isinstance(raw, str) else raw
        except Exception as exc:  # navigation races destroy the execution context
            last = exc
            msg = str(exc)
            if "Execution context was destroyed" not in msg and "Cannot find context" not in msg and "detached" not in msg.lower():
                raise
            await asyncio.sleep(0.08 * (i + 1))
    assert last is not None
    raise last


async def _child_frame(parent: Any, local_ref: int) -> Any | None:
    try:
        handle = await parent.evaluate_handle(RESOLVE_JS, local_ref)
        el = handle.as_element()
        if el is None:
            return None
        return await el.content_frame()
    except Exception:
        return None


def _assign(table: RefTable, frame: Any, data: dict[str, Any], nodes: list[dict[str, Any]], seen_fp: dict[str, int]) -> dict[int, int]:
    """Give every interactive node a stable global ref. Returns local->global map."""
    gen = data.get("gen", "")
    local_to_global: dict[int, int] = {}
    for node in nodes:
        local = node.get("ref")
        if not node.get("op") or local is None:
            continue
        key = (id(frame), gen, int(local))
        ref = table.by_key.get(key)
        fp = _fingerprint(node)
        ordinal = seen_fp.get(fp, 0)
        seen_fp[fp] = ordinal + 1
        fp_key = f"{fp}#{ordinal}"
        if ref is None:
            old = table.by_fp.get(fp_key)
            # reuse an old ref only if its element is gone from this snapshot (re-rendered element)
            if old is not None and old not in local_to_global.values():
                ref = old
            else:
                ref = table.next_ref
                table.next_ref += 1
            table.by_key[key] = ref
        table.by_fp[fp_key] = ref
        table.entries[ref] = RefEntry(
            ref=ref, frame=frame, local=int(local), gen=gen, fingerprint=fp_key, kind=str(node.get("kind", "")),
            op=str(node.get("op", "")), name=str(node.get("name", "")), ctx=str(node.get("ctx", "")),
            click_proxy=int(node.get("click_proxy") or 0),
        )
        local_to_global[int(local)] = ref
    return local_to_global


async def _capture_frame(
    frame: Any, table: RefTable, frame_key: str, opts: dict[str, Any], depth: int, seen_fp: dict[str, int], budget: dict[str, int]
) -> tuple[dict[str, Any], list[dict[str, Any]], list[list[Any]]]:
    data = await _eval_frame(frame, {**opts, "frameKey": frame_key})
    nodes: list[dict[str, Any]] = data.get("nodes", [])
    if depth == 0 and data.get("gen") != table.main_gen:
        table.reset(data.get("gen", ""))
    l2g = _assign(table, frame, data, nodes, seen_fp)
    for n in nodes:
        local = n.get("ref")
        if local is not None and int(local) in l2g:
            n["local_ref"] = int(local)
            n["ref"] = l2g[int(local)]
            if n.get("click_proxy"):
                n["click_proxy"] = int(n["click_proxy"])
        else:
            n["local_ref"] = local
            n["ref"] = None
    flow: list[list[Any]] = []
    out_nodes = list(nodes)
    child_jobs: dict[int, asyncio.Task] = {}
    frames_meta = data.get("frames", [])
    if depth < 2:
        for fm in frames_meta[: max(0, budget["frames"])]:
            budget["frames"] -= 1
            child_jobs[fm["idx"]] = asyncio.ensure_future(_capture_child(frame, fm, table, f"{frame_key}>f{fm['idx']}", opts, depth + 1, seen_fp, budget))
    results: dict[int, tuple | None] = {}
    for idx, task in child_jobs.items():
        try:
            results[idx] = await asyncio.wait_for(task, timeout=4.0)
        except Exception:
            results[idx] = None
    for tok in data.get("flow", []):
        t = tok[0]
        if t == "e":
            g = l2g.get(int(tok[1]))
            if g is not None:
                flow.append(["e", g, tok[2]])
        elif t == "f":
            idx = int(tok[1])
            res = results.get(idx)
            title = tok[2] or ""
            if res is None:
                flow.append(["t", f" [frame{': ' + title if title else ''} (not readable)] "])
            else:
                _cdata, cnodes, cflow = res
                flow.append(["fs", title, tok[3]])
                flow.extend(cflow)
                flow.append(["fe"])
                out_nodes.extend(cnodes)
        else:
            flow.append(tok)
    return data, out_nodes, flow


async def _capture_child(parent: Any, fm: dict[str, Any], table: RefTable, key: str, opts: dict[str, Any], depth: int, seen_fp, budget):
    child = await _child_frame(parent, int(fm["ref"]))
    if child is None:
        return None
    data, nodes, flow = await _capture_frame(child, table, key, opts, depth, seen_fp, budget)
    return data, nodes, flow


async def capture_snapshot(
    page: Any, table: RefTable, *, include_frames: bool = True, max_nodes: int = 3000, budget_ms: int = 600
) -> PageSnapshot:
    opts = {"maxNodes": max_nodes, "budgetMs": budget_ms}
    budget = {"frames": 8 if include_frames else 0}
    seen_fp: dict[str, int] = {}
    data, nodes, flow = await _capture_frame(page.main_frame, table, "main", opts, 0, seen_fp, budget)
    for i, n in enumerate(nodes):
        n["dom_index"] = i
    return PageSnapshot(
        title=data.get("title", ""), url=data.get("url", ""), ready=data.get("ready", ""), gen=data.get("gen", ""),
        scroll=data.get("scroll", {}), nodes=nodes, flow=flow, layer=data.get("layer"),
        frame_count=max(1, len(page.frames)),
        stats=data.get("stats", {}), truncated=bool(data.get("stats", {}).get("truncated")),
    )
