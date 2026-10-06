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
sb captcha submit        # says one of: new round (new image) | same challenge still showing (wrong/incomplete) | gone (likely solved)
```

| Command | Purpose |
|---------|---------|
| `captcha [--pdf]` | Detect + annotate. Output names the provider, kind (`grid`, `text`, `checkbox`, `interstitial`), prompt, image path. |
| `captcha open` | Tick a checkbox-style widget (reCAPTCHA / hCaptcha / Turnstile). Run `captcha` again afterwards: an image challenge may have appeared. |
| `captcha select N …` | Click tiles by badge number. Clicking a selected tile unselects it. |
| `captcha text ANSWER` | Type the characters of a distorted-text CAPTCHA into its input. |
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
* hCaptcha, Turnstile, Arkose, DataDome: **not tested** (detection rules exist for the first two; unverified).

## Honest limits

* Real providers score the *browser*, not just the answer. A headless or freshly-created profile may get endless rounds
  or a hard block; use a headful browser and, where appropriate, a real profile (`--profile` / `--cdp`).
* Press-and-hold, audio and slider/puzzle challenges are detected as `interstitial`/`unknown` and described in text, but
  there is no verb to perform them. Use `shot` and decide whether to hand over to a human.
* Only use this on sites and accounts you are entitled to automate. Many services forbid automated CAPTCHA completion in
  their terms; the tool exists for accessibility, testing and your own properties.
* Results from the local test fixture and Google's public reCAPTCHA demo are recorded in
  [`docs/benchmarks/2026-10-06-dogfood-v1.4.md`](benchmarks/2026-10-06-dogfood-v1.4.md) (§5); nothing is claimed beyond what is listed there.
