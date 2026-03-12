"""Action request validation."""

from __future__ import annotations

from semantic_browser.errors import ActionNotFoundError, ActionStaleError
from semantic_browser.models import ActionDescriptor, ActionRequest, Observation


def resolve_action(request: ActionRequest, observation: Observation) -> ActionDescriptor:
    if request.action_id:
        for action in observation.available_actions:
            if action.id == request.action_id:
                if not action.enabled:
                    raise ActionStaleError(f"Action {request.action_id} is not enabled on current page state.")
                return action
        raise ActionNotFoundError(f"Action {request.action_id} not found.")
    if request.target_id and not request.op:
        target_actions = [a for a in observation.available_actions if a.target_id == request.target_id]
        if target_actions:
            return target_actions[0]
        raise ActionStaleError(f"No action found for target_id={request.target_id}.")
    if request.op:
        candidates = [a for a in observation.available_actions if a.op == request.op]
        if request.target_id:
            candidates = [a for a in candidates if a.target_id == request.target_id]
            if not candidates:
                raise ActionStaleError(f"Action for {request.op}/{request.target_id} not found.")
        if candidates:
            return candidates[0]
        raise ActionNotFoundError(f"No action found for op={request.op}.")
    raise ActionNotFoundError("Action request must include action_id or op.")
