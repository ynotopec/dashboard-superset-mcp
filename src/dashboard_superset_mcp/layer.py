"""SequentialLayer — Semaphore, verify-before-retry, idempotence."""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable

from dashboard_superset_mcp.client import MCPClient, MCPError

logger = logging.getLogger(__name__)


class SequentialLayer:
    """Manages MCP interactions with concurrency control and safety guarantees.

    Enforces three properties:
    1. SEQUENTIAL — one MCP operation at a time (prevents SQLAlchemy session bugs)
    2. VERIFY-THEN-RETRY — verify state before retrying (prevents duplicates)
    3. IDEMPOTENT — deterministic names, check-then-act pattern
    """

    def __init__(
        self,
        client: MCPClient,
        max_retries: int = 3,
        base_delay: float = 1.0,
    ):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self._lock = threading.Lock()
        self._operation_log: list[dict] = []

    @property
    def operation_log(self) -> list[dict]:
        return list(self._operation_log)

    # ── Core execution ────────────────────────────────────────────

    def execute(self, fn: Callable, *args: Any, **kwargs: Any) -> Any:
        """Execute an MCP operation under the semaphore lock."""
        with self._lock:
            fn_name = getattr(fn, "__name__", str(fn))
            logger.info("→ %s", fn_name)
            return fn(*args, **kwargs)

    def retry(
        self,
        fn: Callable,
        *args: Any,
        on_error: Callable[[MCPError, int], bool] | None = None,
        **kwargs: Any,
    ) -> Any:
        """Execute with retry: exponential backoff, max_retries.

        The on_error callback receives (error, attempt) and returns
        True to retry, False to stop. If None, retries on all MCPError.
        """
        last_error: MCPError | None = None
        for attempt in range(self.max_retries + 1):
            try:
                result = self.execute(fn, *args, **kwargs)
                if attempt > 0:
                    logger.info("  ✓ Recovered on attempt %d", attempt + 1)
                return result

            except MCPError as exc:
                last_error = exc
                if attempt < self.max_retries:
                    delay = min(self.base_delay * (2 ** attempt), 30.0)
                    logger.warning(
                        "  ✗ Attempt %d/%d failed: %s — retry in %.1fs",
                        attempt + 1,
                        self.max_retries,
                        exc.message,
                        delay,
                    )
                    time.sleep(delay)

                    if on_error and not on_error(exc, attempt):
                        logger.info("  ⛔ on_error returned False — no retry")
                        break
                else:
                    logger.error(
                        "  ✗ All %d attempts exhausted",
                        self.max_retries + 1,
                    )

        raise MCPError(
            last_error.code if last_error else -1,
            last_error.message if last_error else "All retries exhausted",
        ) from last_error

    # ── Verify-before-retry ───────────────────────────────────────

    def verify_then_action(
        self,
        verify_fn: Callable[..., bool],
        action_fn: Callable[[], dict],
        name: str,
        check_interval: float = 2.0,
        max_wait: float = 15.0,
    ) -> dict:
        """Verify state exists → if not, take action. Prevents duplicates.

        Pattern:
            1. Call verify_fn()
            2. If exists: return existing
            3. If not: call action_fn() → verify → return
        """
        logger.info("  Verify: %s", name)

        # Phase 1: Check if already exists
        try:
            if verify_fn():
                logger.info("  ✓ %s already exists — skipping", name)
                return {"exists": True, "skipped": True}
        except MCPError:
            logger.warning("  Verify failed for %s, proceeding with action", name)

        # Phase 2: Action (with retry)
        try:
            result = self.retry(action_fn)
        except MCPError:
            logger.warning(
                "  Action %s failed, re-checking existence (might have been created)",
                name,
            )
            # Phase 3: Post-action verification (handles the concurrent commit bug)
            self._wait_for(verify_fn, check_interval, max_wait, name)

        return {"exists": False, "created": True}

    def _wait_for(
        self,
        verify_fn: Callable[[], bool],
        interval: float,
        max_wait: float,
        name: str,
    ) -> None:
        """Wait for an object to become available (handles async creation)."""
        elapsed = 0.0
        while elapsed < max_wait:
            time.sleep(min(interval, max_wait - elapsed))
            elapsed += interval
            try:
                if verify_fn():
                    logger.info("  ✓ %s became available after %.1fs", name, elapsed)
                    return
            except MCPError:
                pass

        logger.warning(
            "  ⛔ %s not available after %.1fs timeout",
            name,
            max_wait,
        )

    # ── Deterministic naming ──────────────────────────────────────

    def normalize_name(self, name: str) -> str:
        """Normalize chart/dashboard names for idempotence."""
        import re

        # Lowercase, replace spaces/special chars with underscore
        name = name.lower().strip()
        name = re.sub(r"[^a-z0-9_-]", "_", name)
        name = re.sub(r"_+", "_", name)
        return name

    # ── Operation log ─────────────────────────────────────────────

    def log_operation(
        self,
        operation: str,
        success: bool,
        details: dict | None = None,
        duration: float = 0.0,
    ) -> dict:
        """Record an operation for audit trail."""
        entry = {
            "operation": operation,
            "success": success,
            "details": details or {},
            "duration": round(duration, 3),
        }
        self._operation_log.append(entry)
        return entry
