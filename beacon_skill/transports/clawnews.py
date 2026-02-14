from typing import Any, Dict, List, Optional

import requests

from ..retry import with_retry


class ClawNewsError(RuntimeError):
    pass


class ClawNewsClient:
    """Beacon transport for ClawNews (clawnews.io) — AI agent news aggregator.

    Actions: browse stories, submit stories.
    """

    def __init__(
        self,
        base_url: str = "https://clawnews.io",
        api_key: Optional[str] = None,
        timeout_s: int = 20,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout_s = timeout_s
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "Beacon/1.0.0 (Elyan Labs)"})

    def _request(self, method: str, path: str, auth: bool = False, **kwargs) -> Dict[str, Any]:
        url = f"{self.base_url}{path}"
        headers = kwargs.pop("headers", {})
        if auth:
            if not self.api_key:
                raise ClawNewsError("ClawNews API key required")
            headers = dict(headers)
            headers["Authorization"] = f"Bearer {self.api_key}"
            headers["Content-Type"] = "application/json"

        def _do():
            resp = self.session.request(method, url, headers=headers, timeout=self.timeout_s, **kwargs)
            try:
                data = resp.json()
            except Exception:
                data = {"raw": resp.text}
            if resp.status_code >= 400:
                raise ClawNewsError(data.get("error") or f"HTTP {resp.status_code}")
            return data

        return with_retry(_do)

    def get_stories(self, limit: int = 20) -> List[Dict[str, Any]]:
        result = self._request("GET", f"/api/stories?limit={limit}", auth=True)
        return result.get("stories", result) if isinstance(result, dict) else result

    def submit_story(self, headline: str, url: str, summary: str, tags: Optional[List[str]] = None) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"headline": headline, "url": url, "summary": summary}
        if tags:
            payload["tags"] = tags
        return self._request("POST", "/api/stories", auth=True, json=payload)
