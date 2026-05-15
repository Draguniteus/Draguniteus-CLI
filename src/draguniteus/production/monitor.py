"""Production Monitor: real-time production surveillance and autonomous fixes.

Attach to production environments via HTTP health checks and webhooks:
- Watch for anomalies in real-time
- Detect errors before users notice
- Route alerts via Slack/Discord/webhooks
"""
from __future__ import annotations

import time
import threading
import hashlib
from typing import Any, Callable

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False


class Alert:
    """Alert with severity, deduplication key, and optional metadata."""

    SEVERITY_CRITICAL = "critical"
    SEVERITY_WARNING = "warning"
    SEVERITY_INFO = "info"

    def __init__(self, severity: str, message: str, source: str,
                 metrics: dict | None = None, dedup_key: str | None = None):
        self.severity = severity  # critical, warning, info
        self.message = message
        self.source = source
        self.metrics = metrics or {}
        self.timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ")
        self.dedup_key = dedup_key or self._make_dedup_key(message, source)

    def _make_dedup_key(self, message: str, source: str) -> str:
        key_str = f"{source}:{message[:80]}"
        return hashlib.sha256(key_str.encode()).hexdigest()[:16]

    @property
    def severity_icon(self) -> str:
        return {self.SEVERITY_CRITICAL: "🚨", self.SEVERITY_WARNING: "⚠️", self.SEVERITY_INFO: "ℹ️"}.get(
            self.severity, "•")

    def to_dict(self) -> dict:
        return {
            "severity": self.severity,
            "message": self.message,
            "source": self.source,
            "metrics": self.metrics,
            "timestamp": self.timestamp,
            "dedup_key": self.dedup_key,
        }


class HealthCheck:
    """An HTTP health check to run against a target."""

    def __init__(self, name: str, url: str, method: str = "GET",
                 expected_status: int = 200, timeout: float = 5.0,
                 headers: dict | None = None):
        self.name = name
        self.url = url
        self.method = method.upper()
        self.expected_status = expected_status
        self.timeout = timeout
        self.headers = headers or {}

    def check(self) -> dict[str, Any]:
        """Run the health check. Returns {ok, latency_ms, status, error}."""
        if not HAS_REQUESTS:
            return {"ok": False, "error": "requests library not installed"}

        start = time.time()
        try:
            resp = requests.request(
                self.method, self.url,
                headers=self.headers,
                timeout=self.timeout,
                allow_redirects=True,
            )
            latency_ms = (time.time() - start) * 1000
            ok = resp.status_code == self.expected_status
            return {
                "ok": ok,
                "latency_ms": round(latency_ms, 1),
                "status": resp.status_code,
                "body": resp.text[:200],
            }
        except requests.Timeout:
            return {"ok": False, "latency_ms": (time.time() - start) * 1000,
                    "error": f"Timeout after {self.timeout}s"}
        except requests.ConnectionError as e:
            return {"ok": False, "error": f"Connection error: {e}"}
        except Exception as e:
            return {"ok": False, "error": str(e)}


class ProductionMonitor:
    """Real-time production monitoring with HTTP health checks and webhooks.

    Usage:
        monitor = ProductionMonitor()

        # Add health check targets
        monitor.add_health_check("api-gateway", "https://api.example.com/health")
        monitor.add_health_check("database", "https://db.example.com/ping", method="POST")

        # Register webhook for alerts
        monitor.add_webhook("slack", "https://hooks.slack.com/services/XXX")
        monitor.add_webhook("discord", "https://discord.com/api/webhooks/XXX")

        # Register alert handler
        @monitor.on_alert("critical")
        def fix_it(alert):
            auto_fix(alert)

        monitor.start_watching()
    """

    def __init__(self, check_interval: float = 30.0):
        self.check_interval = check_interval
        self._health_checks: dict[str, HealthCheck] = {}
        self._webhooks: dict[str, str] = {}  # name -> url
        self._alerts: list[Alert] = []
        self._recent_dedup: dict[str, float] = {}  # dedup_key -> last emit timestamp
        self._dedup_window: float = 300.0  # 5 min deduplication window
        self._handlers: dict[str, list[Callable]] = {
            "critical": [], "warning": [], "info": []
        }
        self._running = False
        self._watch_thread: threading.Thread | None = None

    def add_health_check(self, name: str, url: str, method: str = "GET",
                        expected_status: int = 200, timeout: float = 5.0,
                        headers: dict | None = None) -> None:
        """Add a URL to monitor."""
        self._health_checks[name] = HealthCheck(
            name=name, url=url, method=method,
            expected_status=expected_status, timeout=timeout, headers=headers,
        )

    def add_webhook(self, name: str, url: str) -> None:
        """Add a webhook destination for alerts."""
        self._webhooks[name] = url

    def remove_webhook(self, name: str) -> None:
        self._webhooks.pop(name, None)

    def on_alert(self, severity: str) -> Callable:
        """Decorator to register an alert handler."""
        def decorator(func: Callable) -> Callable:
            if severity in self._handlers:
                self._handlers[severity].append(func)
            return func
        return decorator

    def emit_alert(self, alert: Alert, force: bool = False) -> None:
        """Emit an alert with deduplication and webhook delivery."""
        # Deduplication
        if not force and alert.dedup_key in self._recent_dedup:
            elapsed = time.time() - self._recent_dedup[alert.dedup_key]
            if elapsed < self._dedup_window:
                return  # Suppress duplicate
        self._recent_dedup[alert.dedup_key] = time.time()

        self._alerts.append(alert)

        # Call registered handlers
        for handler in self._handlers.get(alert.severity, []):
            try:
                handler(alert)
            except Exception as e:
                print(f"Alert handler error: {e}")

        # Deliver to webhooks
        self._deliver_webhook(alert)

    def _deliver_webhook(self, alert: Alert) -> None:
        """Deliver alert to all configured webhooks."""
        if not HAS_REQUESTS or not self._webhooks:
            return

        payload = alert.to_dict()

        # Format for generic webhook
        generic_payload = {
            "text": f"{alert.severity_icon} [{alert.severity.upper()}] {alert.message}",
            "source": alert.source,
            "timestamp": alert.timestamp,
        }

        # Try Slack format if webhook URL contains slack.com
        slack_payload = {
            "text": f"{alert.severity_icon} *{alert.source}* — {alert.message}",
            "attachments": [{
                "color": {"critical": "danger", "warning": "warning", "info": "#439FE0"}.get(
                    alert.severity, "#cccccc"),
                "fields": [
                    {"title": "Severity", "value": alert.severity, "short": True},
                    {"title": "Source", "value": alert.source, "short": True},
                ],
            }]
        }

        for name, url in self._webhooks.items():
            try:
                if "slack.com" in url:
                    requests.post(url, json=slack_payload, timeout=5)
                else:
                    requests.post(url, json=generic_payload, timeout=5)
            except Exception as e:
                print(f"Webhook '{name}' delivery failed: {e}")

    def start_watching(self) -> str:
        """Start the monitoring loop. Returns status message."""
        if self._running:
            return "Monitor already running."

        if not self._health_checks:
            return "No health checks configured. Use add_health_check() first."

        self._running = True
        self._watch_thread = threading.Thread(
            target=self._watch_loop, daemon=True
        )
        self._watch_thread.start()
        return (f"Production monitor started — watching {len(self._health_checks)} "
                f"target(s), {len(self._webhooks)} webhook(s)")

    def stop_watching(self) -> str:
        """Stop the monitoring loop."""
        if not self._running:
            return "Monitor not running."
        self._running = False
        if self._watch_thread:
            self._watch_thread.join(timeout=5)
        return f"Monitor stopped. {len(self._alerts)} total alerts recorded."

    def _watch_loop(self) -> None:
        """Background monitoring loop — checks all targets on each interval."""
        while self._running:
            for name, check in self._health_checks.items():
                result = check.check()
                if not result.get("ok"):
                    severity = "critical" if "Timeout" in result.get("error", "") else "warning"
                    self.emit_alert(Alert(
                        severity=severity,
                        message=f"{name}: {result.get('error', 'unhealthy')}",
                        source=name,
                        metrics=result,
                    ))
            time.sleep(self.check_interval)

    def get_recent_alerts(self, count: int = 10, severity: str | None = None) -> list[Alert]:
        """Get recent alerts, optionally filtered by severity."""
        alerts = self._alerts[-count:]
        if severity:
            alerts = [a for a in alerts if a.severity == severity]
        return alerts

    def clear_alerts(self) -> None:
        """Clear alert history."""
        self._alerts.clear()
        self._recent_dedup.clear()

    def status_summary(self) -> str:
        """Get a one-line status summary."""
        if not self._running:
            return "Monitor: stopped"

        by_severity: dict[str, int] = {}
        for a in self._alerts[-100:]:  # last 100
            by_severity[a.severity] = by_severity.get(a.severity, 0) + 1

        parts = [f"Monitor: running ({len(self._health_checks)} targets)"]
        if by_severity:
            for sev in ("critical", "warning", "info"):
                if sev in by_severity:
                    parts.append(f"{sev}={by_severity[sev]}")
        return " | ".join(parts)