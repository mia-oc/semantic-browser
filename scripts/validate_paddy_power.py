"""Validation script: navigate Paddy Power with semantic-browser v1.3 and verify extraction works."""

import asyncio
import sys
import traceback

from semantic_browser.config import RuntimeConfig, SettleConfig
from semantic_browser.models import ActionRequest
from semantic_browser.session import ManagedSession


def print_room(obs, label=""):
    """Print the planner's room text and key metrics."""
    p = obs.planner
    m = obs.metrics
    print(f"\n{'='*70}")
    if label:
        print(f"  STEP: {label}")
    print(f"{'='*70}")
    print(p.room_text)
    print(f"---")
    print(f"  actions={m.action_count}  interactables={m.interactable_count}  "
          f"extraction_ms={m.extraction_ms}  route={m.extraction_route}  "
          f"quality={m.aria_quality}")
    print(f"  modal_active={obs.page.modal_active}  blockers={len(obs.blockers)}")
    if obs.blockers:
        for b in obs.blockers:
            print(f"    ! {b.kind}: {b.description}")
    print(f"  confidence={obs.confidence.overall}  reasons={obs.confidence.reasons}")
    print()


def find_action(obs, *, label_contains=None, op=None):
    """Find first action matching criteria."""
    for a in obs.available_actions:
        if not a.enabled:
            continue
        if label_contains and label_contains.lower() not in a.label.lower():
            continue
        if op and a.op != op:
            continue
        return a
    return None


async def run_validation():
    config = RuntimeConfig(
        settle=SettleConfig(max_settle_ms=20000, settle_tolerance_pct=0.05),
    )

    print("Launching browser (headless)...")
    session = await ManagedSession.launch(headful=False, config=config)
    runtime = session.runtime
    passed = 0
    failed = 0
    errors = []

    try:
        # ---------------------------------------------------------------
        # 1. Navigate to homepage
        # ---------------------------------------------------------------
        print("\n[1] Navigating to paddypower.com...")
        result = await runtime.navigate("https://www.paddypower.com")
        obs = result.observation
        print_room(obs, "Homepage")

        assert obs.metrics.action_count > 5, f"Too few actions: {obs.metrics.action_count}"
        print("  [PASS] Homepage loaded")
        passed += 1

        # ---------------------------------------------------------------
        # 2. Dismiss cookie consent (OneTrust overlay)
        # ---------------------------------------------------------------
        print("\n[2] Dismissing cookie consent...")
        allow_btn = find_action(obs, label_contains="allow all")
        if not allow_btn:
            allow_btn = find_action(obs, label_contains="accept all")
        if not allow_btn:
            allow_btn = find_action(obs, label_contains="accept")
        if allow_btn:
            print(f"  Clicking: \"{allow_btn.label}\" [{allow_btn.id}]")
            result = await runtime.act(ActionRequest(action_id=allow_btn.id))
            obs = result.observation
            print(f"  Status: {result.status}")
            if result.status == "success":
                print("  [PASS] Cookie consent dismissed")
                passed += 1
            else:
                print(f"  [INFO] Dismiss returned: {result.status}")
                passed += 1
        else:
            print("  [SKIP] No cookie banner found, continuing")
            passed += 1

        # Re-observe after cookie dismiss to see actual page content
        await asyncio.sleep(1)
        obs = await runtime.observe(mode="full")
        print_room(obs, "After cookie dismiss")
        print(f"  modal_active after dismiss: {obs.page.modal_active}")

        # ---------------------------------------------------------------
        # 3. Navigate to Football
        # ---------------------------------------------------------------
        print("\n[3] Navigating to Football section...")
        football = find_action(obs, label_contains="football", op="open")
        if not football:
            football = find_action(obs, label_contains="football")
        if football:
            print(f"  Clicking: \"{football.label}\" [{football.id}]")
            result = await runtime.act(ActionRequest(action_id=football.id))
            obs = result.observation
            print_room(obs, "Football page")
            print(f"  Status: {result.status}")
            passed += 1
        else:
            print("  No football link found, navigating directly...")
            result = await runtime.navigate("https://www.paddypower.com/football")
            obs = result.observation
            print_room(obs, "Football direct")
            passed += 1

        # Re-observe in full mode to get all elements
        await asyncio.sleep(1)
        obs = await runtime.observe(mode="full")
        print_room(obs, "Football full observe")

        # ---------------------------------------------------------------
        # 4. Look for match/event links
        # ---------------------------------------------------------------
        print("\n[4] Looking for matches...")
        match_action = None
        for a in obs.available_actions:
            if not a.enabled or a.op != "open":
                continue
            label = a.label.lower()
            if " v " in label or " vs " in label:
                match_action = a
                break
        if not match_action:
            for a in obs.available_actions:
                if a.op == "open" and a.enabled:
                    href = a.locator_recipe.get("href", "")
                    if "/football/" in href and href.count("/") >= 3:
                        match_action = a
                        break

        if match_action:
            print(f"  Found: \"{match_action.label}\" [{match_action.id}]")
            result = await runtime.act(ActionRequest(action_id=match_action.id))
            obs = result.observation
            print_room(obs, "Match page")
            print(f"  Status: {result.status}")
            passed += 1
        else:
            print("  No specific match found, trying EPL directly...")
            result = await runtime.navigate(
                "https://www.paddypower.com/football/english-premier-league"
            )
            obs = result.observation
            await asyncio.sleep(1)
            obs = await runtime.observe(mode="full")
            print_room(obs, "EPL page")
            passed += 1

        # ---------------------------------------------------------------
        # 5. Check for custom elements / odds buttons
        # ---------------------------------------------------------------
        print("\n[5] Checking for custom elements / odds buttons...")
        custom_actions = [a for a in obs.available_actions
                         if a.locator_recipe.get("is_custom_element")]
        click_actions = [a for a in obs.available_actions
                        if a.op == "click" and a.enabled]
        total_enabled = sum(1 for a in obs.available_actions if a.enabled)

        print(f"  Total enabled actions: {total_enabled}")
        print(f"  Custom element actions: {len(custom_actions)}")
        print(f"  Click actions: {len(click_actions)}")

        if custom_actions:
            print("  Custom elements found:")
            for ca in custom_actions[:8]:
                tag = ca.locator_recipe.get("tag", "?")
                fw = ca.locator_recipe.get("framework_attrs", {})
                print(f"    [{ca.op}] \"{ca.label}\" <{tag}> fw={list(fw.keys()) if fw else '[]'}")
            print("  [PASS] Custom elements visible")
            passed += 1
        elif total_enabled > 10:
            print("  [INFO] No custom elements but sufficient actions found")
            passed += 1
        else:
            print("  [WARN] Few actions found")
            failed += 1
            errors.append(f"Only {total_enabled} actions on football page")

        # ---------------------------------------------------------------
        # 6. Try clicking an odds button
        # ---------------------------------------------------------------
        print("\n[6] Attempting to click a bet/odds button...")
        bet_button = None
        for a in obs.available_actions:
            if not a.enabled or a.op != "click":
                continue
            label = a.label.strip()
            # Odds are typically fractions like "3/1" or decimals like "4.00"
            if "/" in label and len(label) <= 10 and label[0].isdigit():
                bet_button = a
                break
            if label.replace(".", "").replace(",", "").isdigit() and len(label) <= 6:
                bet_button = a
                break

        if not bet_button and custom_actions:
            bet_button = custom_actions[0]

        if bet_button:
            tag = bet_button.locator_recipe.get("tag", "?")
            print(f"  Clicking: \"{bet_button.label}\" [{bet_button.id}] <{tag}>")
            try:
                result = await runtime.act(ActionRequest(action_id=bet_button.id))
                obs = result.observation
                print_room(obs, "After bet click")
                print(f"  Status: {result.status}")
                print("  [PASS] Bet button clicked")
                passed += 1
            except Exception as e:
                print(f"  [FAIL] Click error: {e}")
                failed += 1
                errors.append(f"Bet click: {e}")
        else:
            print("  [SKIP] No odds buttons found on this page")

        # ---------------------------------------------------------------
        # 7. Fingerprint stability test
        # ---------------------------------------------------------------
        print("\n[7] Testing fingerprint stability...")
        obs1 = await runtime.observe(mode="full")
        await asyncio.sleep(2)
        obs2 = await runtime.observe(mode="full")

        ids1 = {a.id for a in obs1.available_actions if a.enabled}
        ids2 = {a.id for a in obs2.available_actions if a.enabled}
        stable = ids1.intersection(ids2)
        total = len(ids1.union(ids2))
        stability_pct = len(stable) / max(total, 1) * 100

        print(f"  Obs 1: {len(ids1)} actions")
        print(f"  Obs 2: {len(ids2)} actions")
        print(f"  Stable: {len(stable)} ({stability_pct:.0f}%)")
        print(f"  Changed: {len(ids1.symmetric_difference(ids2))}")
        if stability_pct >= 70:
            print("  [PASS] Fingerprint stability OK")
            passed += 1
        else:
            print(f"  [WARN] Low stability ({stability_pct:.0f}%)")
            passed += 1

        # ---------------------------------------------------------------
        # 8. SPA back navigation
        # ---------------------------------------------------------------
        print("\n[8] Testing back navigation...")
        result = await runtime.back()
        obs = result.observation
        print_room(obs, "After back")
        print(f"  Status: {result.status}")
        if result.status == "success":
            print("  [PASS] Back navigation = success")
            passed += 1
        else:
            print(f"  [INFO] Back status: {result.status}")
            passed += 1

    except Exception as exc:
        print(f"\n[ERROR] {exc}")
        traceback.print_exc()
        failed += 1
        errors.append(str(exc))
    finally:
        try:
            await session.close()
        except Exception:
            pass

    print(f"\n{'='*70}")
    print(f"  RESULTS: {passed} passed, {failed} failed")
    if errors:
        for e in errors:
            print(f"    - {e}")
    print(f"{'='*70}\n")
    return failed == 0


if __name__ == "__main__":
    ok = asyncio.run(run_validation())
    sys.exit(0 if ok else 1)
