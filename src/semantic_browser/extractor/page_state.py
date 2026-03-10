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
        () => Boolean(
          document.querySelector('[role="dialog"], [aria-modal="true"], dialog[open]')
        )
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
