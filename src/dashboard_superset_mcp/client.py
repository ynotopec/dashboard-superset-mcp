"""MCP Client — JSON-RPC 2.0 over HTTP."""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class MCPError(Exception):
    """Error returned by MCP server."""

    def __init__(self, code: int, message: str, data: Any = None):
        self.code = code
        self.message = message
        self.data = data
        super().__init__(f"MCP error {code}: {message}")


class MCPClient:
    """Minimal JSON-RPC 2.0 client for Superset MCP server."""

    def __init__(
        self,
        base_url: str,
        timeout: int = 120,
        max_retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 30.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self._token: str | None = None
        self._client = httpx.Client(
            base_url=self.base_url,
            timeout=timeout,
            headers={"Content-Type": "application/json"},
        )

    def _backoff(self, attempt: int) -> float:
        delay = min(self.base_delay * (2 ** attempt), self.max_delay)
        logger.info("  Retry %d/%d — waiting %.1fs", attempt + 1, self.max_retries, delay)
        time.sleep(delay)

    def login(self, username: str, password: str) -> str:
        """Authenticate with Superset and cache JWT token."""
        resp = self._client.post(
            "/api/v1/security/login",
            json={"username": username, "password": password, "provider": "db"},
        )
        if resp.status_code != 200:
            raise MCPError(
                resp.status_code,
                f"Login failed: {resp.text[:200]}",
            )
        token = resp.json()["access_token"]
        self._token = token
        self._client.headers["Authorization"] = f"Bearer {token}"
        logger.info("  Authenticated as %s", username)
        return token

    def list_tools(self) -> list[dict]:
        """Discover available MCP tools."""
        return self._request("list_tools", {})

    def list_resources(self) -> list[dict]:
        """Discover available MCP resources."""
        return self._request("list_resources", {})

    # ── High-level tool wrappers ─────────────────────────────────

    def generate_chart(
        self,
        datasource_id: int,
        viz_type: str,
        metrics: list[str],
        name: str,
        groupby: list[str] | None = None,
        form_data_extra: dict | None = None,
    ) -> dict:
        """Generate a chart and persist it. Returns chart dict with id."""
        form_data = {
            "viz_type": viz_type,
            "datasource": f"{datasource_id}__table",
            "metrics": metrics,
            "datasource_type": "table",
            "datasource_id": datasource_id,
        }
        if groupby:
            form_data["groupby"] = groupby
        if form_data_extra:
            form_data.update(form_data_extra)

        result = self._request(
            "generate_chart",
            {
                "name": name,
                "form_data": form_data,
            },
        )
        return self._ensure_result(result)

    def generate_dashboard(
        self,
        title: str,
        charts: list[dict] | None = None,
        position_json: str | None = None,
    ) -> dict:
        """Generate a dashboard, optionally attaching charts."""
        params: dict[str, Any] = {"title": title}
        if charts:
            params["charts"] = charts
        if position_json:
            params["position_json"] = position_json
        result = self._request("generate_dashboard", params)
        return self._ensure_result(result)

    def add_chart_to_dashboard(
        self,
        dashboard_id: str,
        chart_id: int,
        position: dict | None = None,
    ) -> dict:
        """Add a chart to an existing dashboard."""
        params: dict[str, Any] = {
            "dashboard_id": dashboard_id,
            "chart_id": chart_id,
        }
        if position:
            params["position"] = position
        result = self._request("add_chart_to_existing_dashboard", params)
        return self._ensure_result(result)

    def get_chart_info(self, chart_id: int) -> dict:
        """Get info about a specific chart."""
        return self._request("get_chart_info", {"chart_id": chart_id})

    def list_charts(self, page_size: int = 100) -> list[dict]:
        """List all charts (paginated)."""
        result = self._request("list_charts", {"page_size": page_size})
        return self._ensure_result_list(result)

    def get_dashboard_info(self, dashboard_id: str) -> dict:
        """Get info about a specific dashboard."""
        return self._request("get_dashboard_info", {"dashboard_id": dashboard_id})

    def list_dashboards(self, page_size: int = 100) -> list[dict]:
        """List all dashboards (paginated)."""
        result = self._request("list_dashboards", {"page_size": page_size})
        return self._ensure_result_list(result)

    def create_virtual_dataset(
        self,
        name: str,
        database_id: int,
        schema: str,
        table_name: str,
        sql: str,
    ) -> dict:
        """Create a dataset from a SQL query."""
        params = {
            "name": name,
            "database_id": database_id,
            "schema": schema,
            "table_name": table_name,
            "sql": sql,
        }
        result = self._request("create_virtual_dataset", params)
        return self._ensure_result(result)

    def _ensure_result(self, response: dict) -> dict:
        """Extract the result payload from an MCP response."""
        if "result" in response:
            return response["result"]
        if "data" in response:
            return response["data"]
        # Direct return if no envelope
        if isinstance(response, dict) and "name" in response:
            return response
        return response

    def _ensure_result_list(self, response: dict) -> list[dict]:
        """Extract a list from an MCP response."""
        if "result" in response:
            r = response["result"]
            if isinstance(r, dict) and "objects" in r:
                return r["objects"]
            if isinstance(r, list):
                return r
        if "data" in response:
            d = response["data"]
            if isinstance(d, list):
                return d
        return []

    def _request(self, method: str, params: dict) -> Any:
        """Send a JSON-RPC 2.0 request with retry."""
        for attempt in range(self.max_retries + 1):
            try:
                resp = self._client.post(
                    "/mcp",
                    json={
                        "jsonrpc": "2.0",
                        "id": attempt,
                        "method": method,
                        "params": params,
                    },
                )
                if resp.status_code == 500:
                    body = resp.json()
                    err = body.get("error", {})
                    logger.warning(
                        "MCP 500: %s (%s)",
                        err.get("message", ""),
                        method,
                    )
                    if attempt < self.max_retries:
                        self._backoff(attempt)
                        continue
                    raise MCPError(500, err.get("message", "Internal error"), err.get("data"))

                resp.raise_for_status()
                body = resp.json()
                if "error" in body:
                    err = body["error"]
                    raise MCPError(
                        err.get("code", -1),
                        err.get("message", "Unknown error"),
                        err.get("data"),
                    )
                return body.get("result")

            except (httpx.RequestError, MCPError) as exc:
                if isinstance(exc, MCPError):
                    raise
                if attempt < self.max_retries:
                    self._backoff(attempt)
                    continue
                raise MCPError(-1, f"Network error: {exc}")

        raise MCPError(-1, "Unexpected: loop exited without result")

    def close(self) -> None:
        self._client.close()
