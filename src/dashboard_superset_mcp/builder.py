"""DashboardBuilder — High-level API for creating dashboards."""

from __future__ import annotations

import logging
import time
from typing import Any

from dashboard_superset_mcp.client import MCPClient, MCPError
from dashboard_superset_mcp.config import Settings
from dashboard_superset_mcp.layer import SequentialLayer

logger = logging.getLogger(__name__)


class ChartSpec:
    """Specification for a chart to create."""

    def __init__(
        self,
        name: str,
        viz_type: str,
        datasource_id: int,
        metrics: list[str],
        groupby: list[str] | None = None,
        form_data_extra: dict | None = None,
        column_widths: dict | None = None,
        page_size: int | None = None,
    ):
        self.name = name
        self.viz_type = viz_type
        self.datasource_id = datasource_id
        self.metrics = metrics
        self.groupby = groupby
        self.form_data_extra = form_data_extra or {}
        self.column_widths = column_widths
        self.page_size = page_size

        # Normalize name for idempotence
        self.normalized_name = self._normalize(name)

    @staticmethod
    def _normalize(name: str) -> str:
        import re
        name = name.lower().strip()
        name = re.sub(r"[^a-z0-9_-]", "_", name)
        name = re.sub(r"_+", "_", name)
        return name

    def to_form_data(self) -> dict:
        """Convert to Superset form_data dict."""
        fd = {
            "viz_type": self.viz_type,
            "datasource": f"{self.datasource_id}__table",
            "metrics": self.metrics,
            "datasource_type": "table",
            "datasource_id": self.datasource_id,
        }
        if self.groupby:
            fd["groupby"] = self.groupby
        if self.column_widths:
            fd["column_widths"] = self.column_widths
        if self.page_size:
            fd["page_size"] = self.page_size
        fd.update(self.form_data_extra)
        return fd

    def __repr__(self) -> str:
        return f"ChartSpec({self.normalized_name}, {self.viz_type})"


class DashboardSpec:
    """Specification for a dashboard."""

    def __init__(
        self,
        title: str,
        charts: list[ChartSpec] | None = None,
        existing_dashboard_id: str | None = None,
    ):
        self.title = title
        self.charts = charts or []
        self.existing_dashboard_id = existing_dashboard_id
        self.normalized_title = self._normalize(title)

    @staticmethod
    def _normalize(title: str) -> str:
        import re
        title = title.lower().strip()
        title = re.sub(r"[^a-z0-9_-]", "_", title)
        title = re.sub(r"_+", "_", title)
        return title

    def __repr__(self) -> str:
        n = len(self.charts)
        suffix = f" ({n} charts)" if n > 0 else ""
        return f"DashboardSpec({self.normalized_title}{suffix})"


class DashboardBuilder:
    """High-level orchestrator for dashboard creation.

    Usage:
        settings = Settings.from_env()
        builder = DashboardBuilder(settings)

        dashboard = DashboardSpec(
            title="RNF Analytics",
            charts=[
                ChartSpec("Total RNF", "big_number", 32, ["COUNT(*)"]),
                ChartSpec("Par Etat", "bar", 32, ["COUNT(*)"], groupby=["state_juridique"]),
            ],
        )
        builder.build(dashboard)
    """

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or Settings.from_env()
        self.client = MCPClient(
            base_url=self.settings.mcp.url,
            timeout=self.settings.mcp.timeout,
            max_retries=self.settings.retry.max_retries,
            base_delay=self.settings.retry.base_delay,
            max_delay=self.settings.retry.max_delay,
        )
        self.layer = SequentialLayer(
            client=self.client,
            max_retries=self.settings.retry.max_retries,
            base_delay=self.settings.retry.base_delay,
        )

    def connect(self) -> None:
        """Authenticate with Superset."""
        self.client.login(
            self.settings.superset.username,
            self.settings.superset.password,
        )

    def close(self) -> None:
        self.client.close()

    def build(self, spec: DashboardSpec) -> dict:
        """Execute the full pipeline: dataset → charts → dashboard.

        Returns the dashboard info dict with all details.
        """
        self.connect()
        try:
            logger.info("=== Building dashboard: %s ===", spec.title)
            logger.info("  %d chart(s) to create", len(spec.charts))

            charts_result: list[dict] = []
            if spec.existing_dashboard_id:
                # Add charts to existing dashboard
                logger.info("  Using existing dashboard: %s", spec.existing_dashboard_id)
                for chart_spec in spec.charts:
                    chart = self._create_or_get_chart(chart_spec)
                    charts_result.append(chart)
                    self._add_chart_to_dashboard(
                        spec.existing_dashboard_id,
                        chart,
                        chart_spec,
                    )
            else:
                # Create charts first, then dashboard
                for chart_spec in spec.charts:
                    chart = self._create_or_get_chart(chart_spec)
                    charts_result.append(chart)

                # Create dashboard with all charts
                dashboard = self._create_dashboard(spec, charts_result)

                # Validate the result
                self._validate_dashboard(dashboard)

            result = {
                "success": True,
                "charts": len(charts_result),
                "operation_log": self.layer.operation_log,
            }
            logger.info("=== Build complete: %d charts ===", len(charts_result))
            return result

        except Exception:
            logger.error("=== Build FAILED ===")
            raise
        finally:
            self.close()

    def _create_or_get_chart(self, spec: ChartSpec) -> dict:
        """Create or retrieve an existing chart. Idempotent."""
        result = self.layer.verify_then_action(
            verify_fn=lambda: self._chart_exists(spec.normalized_name),
            action_fn=lambda: self._create_chart(spec),
            name=spec.normalized_name,
        )

        if result.get("exists"):
            # Already existed — fetch its info
            return self._find_chart_by_name(spec.normalized_name)

        # Just created — refresh columns for the datasource
        self._refresh_columns(spec.datasource_id)
        return self._find_chart_by_name(spec.normalized_name)

    def _create_chart(self, spec: ChartSpec) -> dict:
        """Create a single chart via MCP generate_chart."""
        start = time.time()
        try:
            result = self.layer.retry(
                self.client.generate_chart,
                datasource_id=spec.datasource_id,
                viz_type=spec.viz_type,
                metrics=spec.metrics,
                name=spec.name,
                groupby=spec.groupby,
                form_data_extra=spec.form_data_extra,
            )
            duration = time.time() - start
            self.layer.log_operation("create_chart", True, {"name": spec.normalized_name}, duration)
            return result
        except MCPError as exc:
            self.layer.log_operation("create_chart", False, {"name": spec.normalized_name, "error": str(exc)})
            raise

    def _chart_exists(self, normalized_name: str) -> bool:
        """Check if a chart with this normalized name already exists."""
        try:
            charts = self.client.list_charts(page_size=500)
            for chart in charts:
                name = chart.get("slice_name", "").lower()
                norm = name.replace(" ", "_").replace("-", "_")
                if norm == normalized_name or normalized_name in norm:
                    return True
        except MCPError:
            return False
        return False

    def _find_chart_by_name(self, normalized_name: str) -> dict:
        """Find a chart by its normalized name."""
        charts = self.client.list_charts(page_size=500)
        for chart in charts:
            name = chart.get("slice_name", "").lower()
            norm = name.replace(" ", "_").replace("-", "_")
            if norm == normalized_name or normalized_name in norm:
                return chart
        raise MCPError(-1, f"Chart not found: {normalized_name}")

    def _create_dashboard(
        self,
        spec: DashboardSpec,
        charts: list[dict],
    ) -> dict:
        """Create a dashboard and attach all charts."""
        start = time.time()
        try:
            dashboard = self.layer.retry(
                self.client.generate_dashboard,
                title=spec.title,
                charts=[{"chart_id": c["id"]} for c in charts],
            )
            duration = time.time() - start
            self.layer.log_operation(
                "create_dashboard",
                True,
                {"title": spec.normalized_title, "charts": len(charts)},
                duration,
            )
            return dashboard
        except MCPError as exc:
            self.layer.log_operation(
                "create_dashboard",
                False,
                {"title": spec.normalized_title, "error": str(exc)},
            )
            raise

    def _add_chart_to_dashboard(
        self,
        dashboard_id: str,
        chart: dict,
        spec: ChartSpec,
    ) -> None:
        """Add a chart to an existing dashboard."""
        self.client.add_chart_to_dashboard(
            dashboard_id=dashboard_id,
            chart_id=chart["id"],
            position=self._generate_position(chart["id"], spec),
        )

    def _generate_position(
        self,
        chart_id: int,
        spec: ChartSpec,
    ) -> dict:
        """Generate a grid position for the chart.

        Uses a simple top-to-bottom layout.
        """
        # This is a placeholder — in a full implementation,
        # positions would be calculated based on chart specs
        return {
            "chart_id": chart_id,
            "type": "CHART",
            "position": {
                "col": 0,
                "row": 0,
                "rowEnd": 10,
                "colEnd": 24,
            },
        }

    def _validate_dashboard(self, dashboard: dict) -> None:
        """Validate the created dashboard matches expectations."""
        # Re-fetch to ensure persistence
        dashboard_id = dashboard.get("id") or dashboard.get("dashboard_id")
        if not dashboard_id:
            raise MCPError(-1, "Dashboard created but no id returned")

        info = self.client.get_dashboard_info(str(dashboard_id))
        logger.info("  Dashboard validated: %s (id=%s)", info.get("title"), dashboard_id)

        if info.get("charts"):
            logger.info("  Contains %d chart(s)", len(info.get("charts", [])))

    def _refresh_columns(self, datasource_id: int) -> None:
        """Trigger column auto-discovery for a datasource."""
        try:
            self.layer.execute(
                lambda: self.client._client.post(
                    f"/api/v1/dataset/{datasource_id}/refresh/",
                ),
            )
            logger.info("  ✓ Columns refreshed for datasource %d", datasource_id)
        except Exception:
            logger.warning("  Could not refresh columns for datasource %d", datasource_id)
