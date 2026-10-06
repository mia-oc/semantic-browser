# CAPTCHA assist

Visual challenges are hard for text-only agents and trivial for vision models. `sb captcha` bridges the two: it finds
the challenge, **draws numbered badges on the tiles, crops a screenshot (PNG, optionally PDF)**, and performs the clicks
the model asks for. It does not try to solve anything itself.

```
$ sb captcha --pdf
CAPTCHA: provider=recaptcha kind=grid grid=3x3 tiles=9
Prompt: "Select all squares with traffic lights"
Image: /Users/me/.semantic-browser/captcha/captcha-185100-recaptcha-grid.png
PDF: /Users/me/.semantic-browser/captcha/captcha-185100-recaptcha-grid.pdf
Next: look at the image (tiles numbered left->right, top->bottom), then `captcha select N N N`, then `captcha submit`.
```

The agent opens the PNG with its image tool, decides, and answers:

```bash
sb captcha select 2 3 6
sb captcha submit        # says one of: new round (new image) | same challenge still showing | REJECTED (page said so) | ACCEPTED / gone (likely solved)
```

**Canvas puzzles (1.7).** hCaptcha and similar draw their puzzle on a `<canvas>`: there are no tile elements, so `grid=0x0`. `sb captcha` reports
`kind=canvas`, draws a **magenta coordinate ruler** on the image (labels are page CSS pixels, so image pixel = page pixel inside the crop) and prints the
widget's own instruction. Read the point(s) off the ruler, then `captcha click 120,88` or `captcha drag 40,200 180,200`, then `captcha submit`.
After every attempt the tool reads the widget's *visible* error text ("Please try again.") and the page's verdict text ("Correct!" / "Incorrect"), and
says ACCEPTED or REJECTED instead of guessing from whether the challenge disappeared.

| Command | Purpose |
|---------|---------|
| `captcha [--pdf]` | Detect + annotate. Output names the provider, kind (`grid`, `canvas`, `text`, `checkbox`, `interstitial`), prompt, image path. |
| `captcha open` | Tick a checkbox-style widget (reCAPTCHA / hCaptcha / Turnstile). Run `captcha` again afterwards: an image challenge may have appeared. |
| `captcha select N …` | Click tiles by badge number. Clicking a selected tile unselects it. |
| `captcha text ANSWER` | Type the characters of a distorted-text CAPTCHA into its input. |
| `captcha click X,Y [X,Y ...]` | Click page-pixel points read off the image's magenta ruler (canvas puzzles with no tiles). |
| `captcha drag X,Y X,Y [...]` | Press at the first point, move through the rest, release at the last (slider/jigsaw/line-up puzzles). |
| `captcha submit` | Click Verify/Next/Submit, then re-detect. Multi-round challenges return the next annotated image automatically. |
| `captcha refresh` | Ask for a new challenge. |

## How it works

* **Detection** — provider by iframe URL (`recaptcha/api2/anchor|bframe`, `hcaptcha.com … frame=checkbox|challenge`,
  `challenges.cloudflare.com`), generic DOM signals (captcha-named `<img>`/`<input>`), and browser-check pages
  ("Just a moment…").
* **Tiles** — provider selectors first (`td.rc-imageselect-tile`, `.task-image`), otherwise the largest cluster of
  equal-sized visible elements (4–36 of them) in the challenge frame. They are ordered row-major and tagged
  `data-sb-tile=N` so `select N` clicks exactly the element you saw labelled `N`. Numbers are re-assigned every time you
  run `captcha`, because providers swap images between rounds.
* **Image** — badges are injected *inside* the challenge frame (cross-origin frames work), the region is cropped, and the
  badges are removed again so the live page is untouched.
* **PDF** — a dependency-free single-page PDF (caption + JPEG) for pipelines that take documents rather than images.
* **Lite mode** — blocking is lifted for the session as soon as you use `captcha`.

## Verified so far

* Local fixture: grid, wrong-answer and success paths (integration tests).
* Google's **public reCAPTCHA demo**, headless, fresh profile: checkbox found, `open` produced a real 4×4 then 3×3 image grid with its prompt,
  annotated tiles were readable, `select`/`submit` worked, and the second round was detected. Whether Google *accepts* answers depends on
  its risk score for the browser (see below); that was not established.
* **Read as a real model (1.5):** on the same demo I read the numbered image myself and answered a 3×3 *dynamic* grid ("click verify once there
  are none left"): `submit` returned a settled image of the *replacement* tiles, and the demo accepted two rounds before escalating to a 4×4. Two
  fixes came out of this: the image used to be taken mid-fade (it now waits for ~1 s of stillness, 1.6 s minimum after `submit`), and "same
  challenge still showing" no longer claims the answer was wrong — dynamic grids replace the tiles you picked, so look at the new image and
  select what still matches. See [the real-model report](benchmarks/2026-10-06-dogfood-real-model.md).
* **1.7 sweep, public demo pages only** ([report](benchmarks/2026-10-06-competitors-v1.7.md)): reCAPTCHA v2 demo, 8 rounds of image grids including
  multi-round dynamic ones; hCaptcha demo, solved via the canvas kind (two attempts were rejected first, which exposed the false "accepted" signal now
  fixed); Cloudflare Turnstile demo (uses Cloudflare's published testing key, so it proves the plumbing, not a real risk score); captcha.com text
  CAPTCHA, ACCEPTED on the page's "Correct!".
* Arkose/FunCaptcha, DataDome, GeeTest, audio and press-and-hold: **not tested**.

## Honest limits

* Real providers score the *browser*, not just the answer. A headless or freshly-created profile may get endless rounds
  or a hard block; use a headful browser and, where appropriate, a real profile (`--profile` / `--cdp`).
* Production anti-bot gates (e.g. Reddit's "prove your humanity") are described by `sb captcha` but were deliberately **not** attempted.
* Press-and-hold and audio challenges are detected as `interstitial`/`unknown` and described in text, but there is no verb to perform them. Use
  `shot` and decide whether to hand over to a human. Canvas drag/click puzzles are supported, but the coordinates are the model's judgement:
  expect a few rejected attempts (`REJECTED` tells you).
* Scope: the tool was exercised on vendors' own demo pages. Production anti-bot gates (Cloudflare in front of npm/Stack Overflow, Reddit, Fastly,
  DuckDuckGo's anomaly page) were deliberately left alone; the view flags them and says not to retry in a loop.
* Only use this on sites and accounts you are entitled to automate. Many services forbid automated CAPTCHA completion in
  their terms; the tool exists for accessibility, testing and your own properties.
* Results from the local test fixture and Google's public reCAPTCHA demo are recorded in
  [`docs/benchmarks/2026-10-06-dogfood-v1.4.md`](benchmarks/2026-10-06-dogfood-v1.4.md) (§5); nothing is claimed beyond what is listed there.
