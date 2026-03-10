"""Observation delta computation."""

from __future__ import annotations

from semantic_browser.models import Observation, ObservationDelta


def build_delta(previous: Observation | None, current: Observation) -> ObservationDelta:
    if previous is None:
        return ObservationDelta(
            changed_values={"initial_observation": True},
            page_identity_changed=False,
            navigated=False,
            notes=["Initial observation"],
        )

    prev_actions = {a.id: a for a in previous.available_actions}
    curr_actions = {a.id: a for a in current.available_actions}
    enabled_actions = [aid for aid, a in curr_actions.items() if a.enabled and not prev_actions.get(aid, a).enabled]
    disabled_actions = [aid for aid, a in curr_actions.items() if not a.enabled and prev_actions.get(aid, a).enabled]

    prev_blocker_kinds = {b.kind for b in previous.blockers}
    curr_blockers = {b.kind: b for b in current.blockers}
    added_blockers = [b for k, b in curr_blockers.items() if k not in prev_blocker_kinds]
    removed_blocker_kinds = [k for k in prev_blocker_kinds if k not in curr_blockers]

    prev_region_ids = {r.id for r in previous.regions}
    curr_region_ids = {r.id for r in current.regions}
    changed_regions = sorted(list(prev_region_ids.symmetric_difference(curr_region_ids)))

    page_identity_changed = previous.page.page_identity != current.page.page_identity
    navigated = previous.page.url != current.page.url
    return ObservationDelta(
        changed_values={"url": current.page.url} if navigated else {},
        added_blockers=added_blockers,
        removed_blocker_kinds=removed_blocker_kinds,
        enabled_actions=enabled_actions,
        disabled_actions=disabled_actions,
        changed_regions=changed_regions,
        page_identity_changed=page_identity_changed,
        navigated=navigated,
        notes=[],
    )
