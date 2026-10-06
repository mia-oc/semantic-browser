# Vision

An AI should drive a real, headful browser **as fast and as cheaply as it drives a CLI**.

* **Content and options together.** One compact text view where every interactive element is a short number inline in
  the sentence it belongs to — no DOM, no separate action menus, no guessing which of six "Add to basket" buttons is which.
* **CLI-shaped.** `sb goto / click / type / find / scroll / shot` with a persistent browser behind it; output is text a
  small model can act on.
* **Honest.** Every action reports what it did and what changed; failures are loud and specific; stale handles are never
  silently retargeted.
* **Gates are a perception problem, not a wall.** When a CAPTCHA appears, hand a vision model an annotated image and a
  way to answer by number.

## Non-negotiables

1. Public Python API stays backwards compatible (`observe/act/navigate`, `ActionRequest`, legacy `act-*` ids).
2. No credentials in code, docs, logs or fixtures. Gated-site testing is read-only.
3. A change stays only if a benchmark shows it helps (or is neutral and simpler).
4. The thin client stays stdlib-only and starts in milliseconds.
