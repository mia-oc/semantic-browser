"""DOM snapshot helpers."""

from __future__ import annotations


async def capture_dom_stats(page) -> dict:
    return await page.evaluate(
        """
        () => ({
          html_length: (document.documentElement?.outerHTML || '').length,
          forms: document.querySelectorAll('form').length,
          links: document.querySelectorAll('a[href]').length,
          inputs: document.querySelectorAll('input,textarea,select').length,
        })
        """
    )
