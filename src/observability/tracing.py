"""Observability & Tracing — Prometheus metrics for automation tasks.

Provides counters, histograms, and a TracedAgent wrapper that
automatically instruments the AutomationAgent lifecycle.

Architecture reference: §13
"""

import time
from typing import Any, Dict

from loguru import logger

try:
    from prometheus_client import Counter, Gauge, Histogram

    TASK_COUNTER = Counter(
        "automation_tasks_total",
        "Total automation tasks executed",
        ["status"],
    )
    STEP_HISTOGRAM = Histogram(
        "automation_steps_per_task",
        "Steps taken per task",
        buckets=[1, 2, 5, 10, 15, 20, 30],
    )
    LLM_LATENCY = Histogram(
        "llm_request_duration_seconds",
        "LLM API request latency",
        ["provider", "model"],
    )
    ACTIVE_SESSIONS = Gauge(
        "automation_active_sessions",
        "Currently active browser sessions",
    )
    _PROMETHEUS_AVAILABLE = True
except ImportError:
    _PROMETHEUS_AVAILABLE = False
    logger.info(
        "[Tracing] prometheus_client not installed — metrics disabled"
    )


class TracedAgent:
    """Wrapper around AutomationAgent that records Prometheus metrics.

    If prometheus_client is not installed, falls through to the
    underlying agent without any instrumentation.
    """

    def __init__(self, agent):
        """Wrap an AutomationAgent instance.

        Args:
            agent: AutomationAgent instance to instrument
        """
        self.agent = agent

    async def run(self, task: str) -> Dict[str, Any]:
        """Run a task with automatic metrics collection.

        Args:
            task: Natural language task description

        Returns:
            Result dict from the underlying agent
        """
        start = time.time()

        if _PROMETHEUS_AVAILABLE:
            ACTIVE_SESSIONS.inc()

        try:
            result = await self.agent.run(task)

            if _PROMETHEUS_AVAILABLE:
                status = "success" if result.get("success") else "failure"
                TASK_COUNTER.labels(status=status).inc()
                STEP_HISTOGRAM.observe(result.get("steps", 0))

            return result

        except Exception as exc:
            if _PROMETHEUS_AVAILABLE:
                TASK_COUNTER.labels(status="error").inc()
            raise

        finally:
            if _PROMETHEUS_AVAILABLE:
                ACTIVE_SESSIONS.dec()
            elapsed = time.time() - start
            logger.info(
                f"[TracedAgent] Task completed in {elapsed:.2f}s"
            )
