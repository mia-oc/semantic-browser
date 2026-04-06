"""Page metadata capture."""

from __future__ import annotations

from urllib.parse import urlparse

from semantic_browser.models import PageInfo


async def capture_page_info(page, profile_name: str | None = None) -> PageInfo:
    url = page.url or ""
    title = await page.title()
    domain = urlparse(url).netloc
    ready_state = await page.evaluate("document.readyState")
    frame_count = len(page.frames)
    modal_active = await page.evaluate(
        """
        () => {
          // Tier 1: standard ARIA — only if the dialog is actually visible
          const ariaDialogs = document.querySelectorAll('[role="dialog"], [aria-modal="true"], dialog[open]');
          for (const el of ariaDialogs) {
            const s = getComputedStyle(el);
            const r = el.getBoundingClientRect();
            if (s.display !== 'none' && s.visibility !== 'hidden'
                && r.width > 0 && r.height > 0 && s.opacity !== '0')
              return true;
          }

          // Tier 2: class-based heuristic for framework modals/overlays
          const candidates = document.querySelectorAll(
            '[class*="modal"], [class*="overlay"], [class*="Modal"], [class*="Overlay"]'
          );
          for (const el of candidates) {
            const s = getComputedStyle(el);
            if (s.display === 'none' || s.visibility === 'hidden'
                || s.opacity === '0' || el.offsetWidth === 0) continue;
            const pos = s.position;
            if (pos === 'fixed' || pos === 'absolute' || el.parentElement === document.body)
              return true;
          }

          // Tier 2b: custom-element modals (hyphenated tags containing modal/overlay/dialog)
          const customModals = document.querySelectorAll(
            '*'
          );
          for (const el of customModals) {
            const tag = el.tagName.toLowerCase();
            if (!tag.includes('-')) continue;
            if (!(tag.includes('modal') || tag.includes('overlay')
                || tag.includes('dialog') || tag.includes('popup'))) continue;
            const s = getComputedStyle(el);
            if (s.display !== 'none' && s.visibility !== 'hidden'
                && s.opacity !== '0' && el.offsetWidth > 0)
              return true;
          }

          // Tier 3: viewport coverage heuristic
          const vw = window.innerWidth, vh = window.innerHeight;
          const vpArea = vw * vh;
          const allEls = document.querySelectorAll('*');
          for (const el of allEls) {
            const s = getComputedStyle(el);
            if (s.position !== 'fixed' && s.position !== 'absolute') continue;
            const z = parseInt(s.zIndex) || 0;
            if (z <= 100) continue;
            if (s.opacity === '0' || s.display === 'none' || s.visibility === 'hidden') continue;
            const r = el.getBoundingClientRect();
            if (r.width * r.height > vpArea * 0.5) return true;
          }

          return false;
        }
        """
    )
    page_type = await page.evaluate(
        """
        () => {
          if (document.querySelector('form input[type="password"]')) return 'login';
          if (document.querySelector('article')) return 'article';
          if (document.querySelector('table')) return 'table';
          if (document.querySelector('main form')) return 'form';
          return 'generic';
        }
        """
    )
    page_identity = f"{domain}:{title.strip().lower()[:64]}"
    return PageInfo(
        url=url,
        title=title,
        domain=domain,
        page_type=(page_type or "generic"),
        page_identity=page_identity,
        ready_state=ready_state,
        modal_active=modal_active,
        frame_count=frame_count,
        profile_name=profile_name,
    )
