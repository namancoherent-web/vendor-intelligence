"""HTTP fetch shim for crawler/smart_crawl.py (no changes to smart_crawl)."""
from __future__ import annotations

import httpx


class FetchResponse:
    def __init__(self, status_code: int, content: bytes, text: str) -> None:
        self.status_code = status_code
        self.content = content
        self.text = text


async def safe_fetch(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    timeout: float = 12.0,
) -> FetchResponse:
    async with httpx.AsyncClient(follow_redirects=False, timeout=timeout) as client:
        resp = await client.get(url, headers=headers or {})
        content = resp.content or b""
        return FetchResponse(resp.status_code, content, resp.text)
