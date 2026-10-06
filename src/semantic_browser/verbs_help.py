"""Verb reference shown by `sb help` (stdlib-only so the thin client can print it instantly)."""

HELP = """\
sb verbs (every verb prints the resulting page view; act on the [n] numbers you see in it):
  goto URL                    open a page            | view [--page N|--full|--all|--expand nav]  re-read / window / overlay-off / unfold
  click N [--force] [--right] click [n]               | type N "text" [--enter] [--append]   fill an input
  select N "option"           choose a <select> option| check N                    toggle checkbox/radio/switch
  press KEY [N]               Enter, Escape, Tab...   | hover N                    reveal hover menus
  dblclick N                  double-click [n]        | drag FROM TO               drag [n] onto [n]
  upload N PATH [PATH...]     attach files to a `file` control (credential-looking files are refused)
  scroll [down|up|top|bottom] [N]  move the viewport  | find TEXT                  search the whole page for text
  wait [MS | text "T"]        pause or wait for text  | back | forward | reload
  tabs | tab N                list / switch tabs      | shot [--marks] [--full] [PATH]   screenshot (marks = [n] boxes)
  captcha [--pdf]             detect + annotate a challenge as an image
  captcha open|select N..|text ANSWER|submit|refresh   act on it
  do "STEP" "STEP" ...        run several verbs in ONE call (stops at first failure; prints the last view)
  guide [--skill]             print the agent playbook (how to use sb well; --skill = SKILL.md form)
  close                       end the session
Targets are the [n] numbers; a unique visible label also works (click "Sign in"). Ambiguous labels list the candidates.
Example: sb do "type 3 boots --enter" "click Football" view      (fewer round trips = faster tasks)
New here? Run `sb guide` once: the loop, how to read the view, recovery, bot walls and safety rules.
Tips: if a view ends with "... more below" use `scroll down` (or `view --page 2`). If a click says "blocked", dismiss the
overlay it names first. Refs are stable while the page stays the same; after navigation always use the new view's numbers.
"""
