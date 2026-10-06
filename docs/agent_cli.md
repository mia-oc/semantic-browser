# `sb` — the agent CLI (v1.7)

> Giving this to an AI? Start with **[agent_guide.md](agent_guide.md)** (`sb guide`): the short playbook. This page is the reference.

`sb` is how an AI (or a shell script) drives a real, headful Chromium with one short command per step. A background
daemon keeps the browser alive between commands, so a call that does not touch the page (`find`, `view`) takes about 45-110 ms end to end
(5 timed calls on 1.7, including Python start-up); actions add the page's own time and a short settle (typically 0.2-0.4 s).

```bash
sb goto news.ycombinator.com        # opens the page, prints the view
sb click 12                         # act on the [12] you saw in the view
sb type 3 "hello world" --enter     # fill + submit
sb find "price"                     # search the whole page, not just the visible window
sb do "type 3 boots --enter" "click Football" view   # several verbs in ONE call (one model turn)
sb shot --marks                     # screenshot with [n] boxes drawn on the elements
sb stop                             # shut the browser down (it also exits after 15 idle minutes)
```

Every verb prints **one outcome line + the resulting page view**, so a model never has to ask "what happened?":

```
filled and submitted [1] 'Search catalogue' page changed (+4/-1 lines): …

@ results:anvil — http://127.0.0.1:8080/search   [screen 1/1]
# Catalogue
[1 input:search "Search catalogue"="anvil"] [2 button]Search
- [3]Anvil Classic £49.99 In stock
- [4]Anvil Pro £89.50 Low stock
- [5]Anvil Mini £24.99 In stock
```

## Reading the view

| Syntax | Meaning |
|--------|---------|
| `[7]Docs` | link; `click 7` follows it |
| `[7 button]Save` | button |
| `[3 input "Email"="a@b.c"]` | text input with its current value (`input:password`, `input:search` …) |
| `[5 slider "Volume"="7" 0..10]` | range input with its current value and bounds; `type 5 7` |
| `[8 file "CV"]` | file input; `upload 8 /path` (clicking it is an error that says so) |
| `[5 select "Size"="M" {S\|M\|L}]` | `<select>` with its options; `select 5 "L"` |
| `[6 checkbox ✓]Agree` | checkbox/radio/switch; `check 6` toggles |
| `[9 covered]` | something else is on top of it; clicking will say what. Dismiss the overlay first |
| `Foo — ctx` | a duplicate label; the text after the dash says which one (e.g. which product) |
| `nav: [1]A [2]B … (+9 more …)` | collapsed navigation/footer; `view --expand nav` (or `footer`/`aside`/`all`) unfolds it |
| `⟦frame: Payment⟧` | content inside an iframe (cross-origin too). Refs inside work like any other |
| `! BLOCKING OVERLAY "Cookies" … dismiss with [4]` | a modal/consent layer hides the page; handle it first. The hint ranks close/reject/short-accept and never suggests sign-in, subscribe or pay. With no safe control it says `no obvious dismiss control` and lists the options. `view --all` shows the page behind it |
| `! This looks like a bot/verification page …` | the site is showing a bot wall / human check / rate limit. Do not loop; `sb captcha` only if solving is part of the task, else report it |
| `[7](unlabeled → /cart)` | a control with no text; for links the destination is shown |
| `· \| · \| [95]1` | in tables that have `<th>` headers, `·` marks an empty cell so columns stay aligned |
| `… more below (~900 tokens)` | the view is windowed (default ≈ 5 000 chars). `scroll down` or `view --page 2` |

Refs are **stable while the page stays the same** (including across re-renders of the same element). Numbers are
**never reused within a session**: after a navigation the new page gets new numbers, and using an old one is rejected
(`INVALID: ref 9 not found …` / `STALE:`), never silently retargeted to a different element.

Instead of a number you may write a visible label: `click "Sign in"` (quotes optional: `click Save settings`). It acts when exactly one
element has that label, or when every match goes to the same destination (nav + footer links). Otherwise the error lists the candidates with
where each goes (`3 elements match 'Sport': [17] Sport → /sport; [105] Sport → /uk/sport`). Numbers remain the precise way, and refs are
**per session**: never type a number from an earlier session.

## Verbs

| Verb | What it does |
|------|--------------|
| `goto URL` | Navigate (adds `https://` if no scheme). |
| `view [--page N] [--full] [--all] [--expand KIND]` | Fresh view. `--page` walks the windowed view without touching the browser; `--full` is the whole page; `--all` shows the page behind a blocking overlay; `--expand nav` unfolds a collapsed landmark. Unknown options are an error. |
| `click N [--force] [--right]` | Click `[N]`. If the element is covered you get `blocked: … covered by <tag> "text"`. `--right` opens the context menu. |
| `dblclick N` | Double-click `[N]`. |
| `drag FROM TO` | Drag `[FROM]` onto `[TO]` (HTML5 drag-and-drop and mouse-driven sortables; 12 intermediate mouse moves). |
| `upload N PATH [PATH…]` | Set files on a file input `[N]`. Refuses key/credential paths (`~/.ssh`, `.env`, `*.pem` …) and files over the size cap. |
| `type N "text" [--enter] [--append]` | Fill an input (finds the real `<input>` inside wrappers/custom elements). `--enter` submits. |
| `select N "label"` | Choose an option; on custom (div) dropdowns it opens them and the next view lists the options. |
| `check N` | Toggle a checkbox/radio/switch; verifies the state really changed (works for visually hidden inputs via their label). |
| `press KEY [N]` | Press a key (Enter, Escape, Tab, ArrowDown…), optionally focusing `[N]` first. |
| `hover N` | Reveal hover menus. |
| `scroll [down\|up\|top\|bottom] [N]` | Scrolls the window or the page's main scroll container (N screenfuls, 1–20); reports if already at the end. |
| `find TEXT` | Case-insensitive search across the **entire** page (also behind an overlay). Long lines are centred on the match; a table row is followed by `↳ columns:` taken from its real `<th>` header row (omitted when there is none). Whole-word hits are listed first (and counted); a short hit like a bare price carries the line before it. Capped at 15 hits, and says so. |
| `do "STEP" "STEP" …` | Up to 12 verbs in one call (e.g. `do "click 3" "type 4 hello --enter" view`). Stops at the first failure (`stopped at step 2 of 5:` + that step's output). Intermediate steps print a one-line outcome; the last prints its full view. `close` and nested `do` are not allowed. |
| `wait [MS]` / `wait text "T" [MS]` | Pause, or poll until text appears. |
| `back` `forward` `reload` | History. |
| `tabs` / `tab N` | Popups are adopted automatically ("opened in a new tab; now viewing it"); use these to switch. |
| `shot [--marks] [--full] [PATH]` | PNG screenshot. `--marks` draws a box + number on every ref in the viewport. |
| `captcha …` | `captcha`, `open`, `select`, `text`, `click X,Y`, `drag X,Y X,Y`, `submit`, `refresh`. See [captcha.md](captcha.md). |
| `guide [--skill]` | Print the agent playbook (works with no browser running). `--skill` wraps it as a SKILL.md. |
| `close` | End the session. |

JavaScript `alert/confirm/prompt` dialogs are auto-accepted and reported as a note in the next view. Caution: that means a
"Delete everything?" `confirm()` is accepted too; give agents read-only tasks unless you intend otherwise.

## Outcomes and exit codes

The first line starts with one of `FAILED:` / `STALE:` / `INVALID:` / `BLOCKED:` / `ERROR:` when something went wrong
(exit code 1). Otherwise exit code 0 and the line says what changed: `-> now at 'Title' (url)`, `overlay dismissed`,
`an overlay appeared and covers the page`, `page changed (+3/-1 lines): …`, `page title is now '…'` (many forms signal success only via the title), or `no visible change on the page`.

## Sessions and options

```bash
sb --session work --profile ~/.sb/work goto https://intranet     # separate browser + persistent profile
sb --headless goto example.com                                    # default is headful (many sites block headless)
sb --cdp http://127.0.0.1:9222 view                               # drive an already-running Chrome
sb --lite media goto https://heavy-site.example                   # skip images/fonts/video + disable animations
sb sessions                                                       # list daemons
sb stop [NAME|--all]
```

Session options only matter on the call that *starts* the daemon. Environment equivalents: `SB_SESSION`,
`SB_HEADLESS=1`, `SB_PROFILE`, `SB_CDP`, `SB_LITE`, `SB_HOME` (state dir, default `~/.semantic-browser`).

### Lite mode

`--lite media` blocks images, fonts and video **by resource type** (never by URL text, which broke Wikipedia in testing) and
injects a no-animation stylesheet; `--lite max` also blocks well-known trackers. CAPTCHA provider hosts are allow-listed and the
`captcha` verb switches blocking off for the rest of the session. **Measured benefit: none reliable** on the 1.7 benchmark set
(navigation 417-439 ms with lite vs 339-434 ms without; live suite 1.69 s vs 1.93 s, within run-to-run swing; [results](benchmarks/2026-10-06-v1.7-suites.md)), so it is off by default; it may help on slow connections (untested).

## From Python

```python
from semantic_browser.agent import AgentSession

s = await AgentSession.launch(headful=True)          # or cdp="http://127.0.0.1:9222"
print(await s.run("goto example.com"))
print(await s.run('type 3 "hello" --enter'))
await s.close()
```

`AgentSession.run()` accepts the same strings as the CLI and never raises for page problems; it returns text.

## Security model

* The daemon listens only on a unix socket in a `0700` directory (`~/.semantic-browser/run/<name>.sock`, mode `0600`).
  Any process running as the same OS user can drive the browser — treat it like the browser profile itself.
* No network listener is opened. Session names are restricted to `[A-Za-z0-9_-]{1,32}`.
* `shot PATH` and `captcha` write files with your user's permissions; captcha images go under
  `~/.semantic-browser/captcha/`.
* `--cdp` attaches to a browser a person may be using: the session works in **one tab it opened**, lists/switches/adopts only its own
  tabs (other tabs' titles never reach the model) and closes only its own tab on exit.
* Password, card-number (`cc-*`) and one-time-code fields are masked in the view. Screenshots and captcha images can still contain
  whatever is on the page; their directories are `0700`.
* With `--profile`/`--cdp` the browser carries real logins. The CLI performs exactly what it is told, so give agents
  read-only tasks unless you intend otherwise.

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `could not start the browser daemon` | The message now shows the root-cause line and the usual fix (`semantic-browser install-browser`; for `--cdp`, start Chrome with `--remote-debugging-port`). Full log: `~/.semantic-browser/run/<name>.log`. |
| `note: restarting session … because semantic-browser was updated` | Expected after `pip install -U`: the old daemon ran old code, so it was restarted (page state is reset). |
| `ERROR: timed out` | A page is hanging. `sb view` (fresh) or `sb reload`; `sb stop` as a last resort. |
| Blank view `(no visible content yet …)` | Page still rendering or bot-gated: `sb wait 1500` then `sb view`; try `sb shot`. |
| Everything says `covered` | A full-page overlay you have not dismissed; look for the `! BLOCKING OVERLAY` line. |
