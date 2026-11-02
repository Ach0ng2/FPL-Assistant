"""Client FPL Public API dengan cache disk sederhana.

API publik tidak butuh login, tapi menolak request tanpa User-Agent browser.
Data dari GW yang sudah selesai (picks, live) tidak akan berubah, jadi
di-cache permanen; sisanya pakai TTL.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import httpx

BASE_URL = "https://fantasy.premierleague.com/api"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"
)


class FPLClient:
    def __init__(
        self,
        cache_dir: Path | None = None,
        ttl_seconds: int = 1800,
        client: httpx.Client | None = None,
        max_retries: int = 3,
    ) -> None:
        self.cache_dir = cache_dir
        self.ttl = ttl_seconds
        self.max_retries = max_retries
        self._http = client or httpx.Client(
            base_url=BASE_URL,
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
            timeout=20.0,
            follow_redirects=True,
        )
        self._mem: dict[str, Any] = {}

    # ---------- infra ----------
    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> FPLClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def _cache_path(self, path: str) -> Path | None:
        if not self.cache_dir:
            return None
        safe = path.strip("/").replace("/", "_").replace("?", "_").replace("=", "-")
        return self.cache_dir / f"{safe or 'root'}.json"

    def get(self, path: str, *, permanent: bool = False) -> Any:
        """GET `path` (relatif ke BASE_URL). `permanent=True` = jangan pernah kedaluwarsa."""
        if path in self._mem:
            return self._mem[path]

        cache_file = self._cache_path(path)
        if cache_file and cache_file.exists():
            age = time.time() - cache_file.stat().st_mtime
            if permanent or age < self.ttl:
                data = json.loads(cache_file.read_text(encoding="utf-8"))
                self._mem[path] = data
                return data

        data = self._fetch(path)
        self._mem[path] = data
        if cache_file:
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            cache_file.write_text(json.dumps(data), encoding="utf-8")
        return data

    def _fetch(self, path: str) -> Any:
        last_exc: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                resp = self._http.get(path)
                if resp.status_code == 429 or resp.status_code >= 500:
                    raise httpx.HTTPStatusError(
                        f"HTTP {resp.status_code}", request=resp.request, response=resp
                    )
                resp.raise_for_status()
                return resp.json()
            except (httpx.TransportError, httpx.HTTPStatusError) as exc:
                last_exc = exc
                status = getattr(getattr(exc, "response", None), "status_code", None)
                if status is not None and 400 <= status < 500 and status != 429:
                    raise
                time.sleep(1.5 * (attempt + 1))
        assert last_exc is not None
        raise last_exc

    # ---------- endpoints ----------
    def bootstrap(self) -> dict[str, Any]:
        return self.get("/bootstrap-static/")

    def fixtures(self) -> list[dict[str, Any]]:
        return self.get("/fixtures/")

    def element_summary(self, element_id: int) -> dict[str, Any]:
        return self.get(f"/element-summary/{element_id}/")

    def entry(self, team_id: int) -> dict[str, Any]:
        return self.get(f"/entry/{team_id}/")

    def entry_history(self, team_id: int) -> dict[str, Any]:
        return self.get(f"/entry/{team_id}/history/")

    def entry_transfers(self, team_id: int) -> list[dict[str, Any]]:
        return self.get(f"/entry/{team_id}/transfers/")

    def entry_picks(self, team_id: int, gw: int, *, finished: bool = False) -> dict[str, Any]:
        return self.get(f"/entry/{team_id}/event/{gw}/picks/", permanent=finished)

    def event_live(self, gw: int, *, finished: bool = False) -> dict[str, Any]:
        return self.get(f"/event/{gw}/live/", permanent=finished)

    def league_standings(self, league_id: int) -> list[dict[str, Any]]:
        """Semua baris standings (menangani paginasi)."""
        results: list[dict[str, Any]] = []
        page = 1
        while True:
            data = self.get(f"/leagues-classic/{league_id}/standings/?page_standings={page}")
            results.extend(data["standings"]["results"])
            if not data["standings"].get("has_next"):
                break
            page += 1
        return results

    def league_info(self, league_id: int) -> dict[str, Any]:
        return self.get(f"/leagues-classic/{league_id}/standings/?page_standings=1")["league"]
