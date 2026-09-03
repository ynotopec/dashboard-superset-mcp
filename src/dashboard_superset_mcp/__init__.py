"""Dashboard Superset MCP — Automate Superset dashboards via native MCP."""

__version__ = "0.0.0"

from dashboard_superset_mcp.config import Settings
from dashboard_superset_mcp.client import MCPClient
from dashboard_superset_mcp.layer import SequentialLayer
from dashboard_superset_mcp.builder import DashboardBuilder

__all__ = [
    "Settings",
    "MCPClient",
    "SequentialLayer",
    "DashboardBuilder",
]
