import logging

import pytest

from app.core.logging import QuietAccessFilter, configure_logging


def rec(method: str, path: str, status: int) -> logging.LogRecord:
    return logging.LogRecord(
        "uvicorn.access",
        logging.INFO,
        "",
        0,
        '%s - "%s %s HTTP/%s" %d',
        ("172.19.0.5:39636", method, path, "1.1", status),
        None,
    )


@pytest.mark.parametrize(
    ("method", "path", "status", "kept"),
    [
        ("GET", "/api/v1/system/summary", 200, False),
        ("GET", "/api/v1/instances", 200, False),
        ("GET", "/api/v1/instances/abc123", 200, False),
        ("GET", "/api/v1/instances/abc123/events", 200, False),
        ("GET", "/api/v1/instances/abc123/metrics", 200, False),
        ("GET", "/api/v1/logs/sources", 200, False),
        ("GET", "/api/v1/downloads", 200, False),
        ("GET", "/api/v1/model-details/local:Qwen2.5-7B", 200, False),
        ("GET", "/api/v1/presets?model_id=local:x", 200, True),
        ("GET", "/healthz", 200, False),
        ("GET", "/api/v1/system/summary", 500, True),
        ("GET", "/api/v1/instances", 401, True),
        ("POST", "/api/v1/instances/abc123/start", 202, True),
        ("POST", "/api/v1/auth/login", 200, True),
        ("DELETE", "/api/v1/instances/abc123", 204, True),
        ("GET", "/api/v1/instances/abc123/logs/stream", 200, True),
    ],
)
def test_quiet_filter(method: str, path: str, status: int, kept: bool) -> None:
    assert QuietAccessFilter().filter(rec(method, path, status)) is kept


def test_configure_toggles() -> None:
    access = logging.getLogger("uvicorn.access")
    configure_logging(verbose_access=False)
    assert any(isinstance(f, QuietAccessFilter) for f in access.filters)
    assert logging.getLogger("httpx").level == logging.WARNING
    configure_logging(verbose_access=False)
    assert sum(isinstance(f, QuietAccessFilter) for f in access.filters) == 1
    configure_logging(verbose_access=True)
    assert not any(isinstance(f, QuietAccessFilter) for f in access.filters)
    assert logging.getLogger("httpx").level == logging.INFO
    configure_logging(verbose_access=False)
