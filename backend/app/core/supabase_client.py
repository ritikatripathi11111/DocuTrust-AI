"""Supabase data access layer.

A thin, typed wrapper around the Supabase PostgREST API. We use httpx directly
rather than the supabase-py SDK to keep the dependency footprint small and the
behavior explicit. All writes go through the anon key so RLS policies are
exercised exactly as the frontend would exercise them.
"""
from __future__ import annotations

import json
from typing import Any, Optional

import httpx

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class SupabaseError(RuntimeError):
    """Raised when a Supabase REST call fails."""


class SupabaseClient:
    """Minimal PostgREST client used by the backend services."""

    def __init__(
        self,
        url: str,
        anon_key: str,
        service_role_key: str = "",
        *,
        timeout: float = 30.0,
    ) -> None:
        self._base_url = url.rstrip("/")
        self._anon_key = anon_key
        self._service_role_key = service_role_key
        self._timeout = timeout

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "apikey": self._anon_key,
            "Authorization": f"Bearer {self._anon_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    @property
    def _admin_headers(self) -> dict[str, str]:
        # Service role key bypasses RLS; only used for internal diagnostics.
        key = self._service_role_key or self._anon_key
        return {
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _request(
        self,
        method: str,
        path: str,
        *,
        headers: dict[str, str],
        params: Optional[dict[str, Any]] = None,
        json_body: Optional[Any] = None,
    ) -> Any:
        url = f"{self._base_url}{path}"
        try:
            with httpx.Client(timeout=self._timeout) as client:
                response = client.request(
                    method, url, headers=headers, params=params, json=json_body
                )
        except httpx.RequestError as exc:
            raise SupabaseError(f"network error: {exc}") from exc

        if response.status_code >= 400:
            raise SupabaseError(
                f"supabase {method} {path} -> {response.status_code}: {response.text}"
            )
        if response.status_code == 204 or not response.text:
            return None
        try:
            return response.json()
        except json.JSONDecodeError as exc:
            raise SupabaseError(f"invalid json from supabase: {exc}") from exc

    # --- Table operations ---

    def insert(self, table: str, row: dict[str, Any]) -> dict[str, Any]:
        result = self._request(
            "POST",
            f"/rest/v1/{table}",
            headers={**self._headers, "Prefer": "return=representation"},
            json_body=row,
        )
        if isinstance(result, list) and result:
            return result[0]
        return result or {}

    def insert_many(self, table: str, rows: list[dict[str, Any]]) -> None:
        """Insert multiple rows in a single request. PostgREST accepts an array."""
        if not rows:
            return
        self._request(
            "POST",
            f"/rest/v1/{table}",
            headers={**self._headers, "Prefer": "return=minimal"},
            json_body=rows,
        )

    def update(
        self,
        table: str,
        filters: dict[str, Any],
        values: dict[str, Any],
    ) -> list[dict[str, Any]]:
        params = {f"{k}": f"eq.{v}" for k, v in filters.items()}
        result = self._request(
            "PATCH",
            f"/rest/v1/{table}",
            headers={**self._headers, "Prefer": "return=representation"},
            params=params,
            json_body=values,
        )
        return result if isinstance(result, list) else []

    def select(
        self,
        table: str,
        *,
        filters: Optional[dict[str, Any]] = None,
        columns: str = "*",
        order: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"select": columns}
        if filters:
            for k, v in filters.items():
                params[k] = f"eq.{v}"
        if order:
            params["order"] = order
        if limit is not None:
            params["limit"] = limit
        result = self._request("GET", f"/rest/v1/{table}", headers=self._headers, params=params)
        return result if isinstance(result, list) else []

    def select_one(
        self,
        table: str,
        *,
        filters: dict[str, Any],
        columns: str = "*",
    ) -> Optional[dict[str, Any]]:
        rows = self.select(table, filters=filters, columns=columns, limit=1)
        return rows[0] if rows else None

    def delete(self, table: str, filters: dict[str, Any]) -> None:
        params = {f"{k}": f"eq.{v}" for k, v in filters.items()}
        self._request(
            "DELETE",
            f"/rest/v1/{table}",
            headers=self._headers,
            params=params,
        )

    # --- RPC (for vector similarity search) ---

    def rpc(self, fn: str, params: dict[str, Any]) -> Any:
        result = self._request(
            "POST",
            f"/rest/v1/rpc/{fn}",
            headers=self._headers,
            json_body=params,
        )
        return result


def get_supabase_client() -> SupabaseClient:
    """Return a fresh client configured from settings."""
    if not settings.supabase_url or not settings.supabase_anon_key:
        raise SupabaseError("Supabase URL and anon key must be configured")
    return SupabaseClient(
        url=settings.supabase_url,
        anon_key=settings.supabase_anon_key,
        service_role_key=settings.supabase_service_role_key,
    )
