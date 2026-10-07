import logging
import re

# Polling endpoints the Web Console calls every few seconds; successful GETs are not logged.
QUIET_PATHS = re.compile(
    r"^/(healthz"
    r"|api/v1/(system/(summary|info|autostart|external)"
    r"|instances(/[^/\s]+(/(events|metrics|logs))?)?"
    r"|logs/sources"
    r"|downloads"
    r"|models|model-sources|model-details/\S+"
    r"|gateway/(status|connection-info|models|keys)"
    r"|settings/(api-base|hf-token)"
    r"|auth/me))(\?\S*)?$"
)


class QuietAccessFilter(logging.Filter):
    """Drop uvicorn access lines for successful polling GETs. Keeps writes, errors and logins."""

    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        if not isinstance(args, tuple) or len(args) < 5:
            return True
        method, path, status = args[1], str(args[2]), str(args[4])
        try:
            ok = 200 <= int(status) < 300
        except (TypeError, ValueError):
            return True
        return not (method in ("GET", "HEAD") and ok and QUIET_PATHS.match(path))


def configure_logging(verbose_access: bool) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    # httpx logs every outgoing request at INFO (LiteLLM readiness, model/info, vLLM probes); keep failures only.
    logging.getLogger("httpx").setLevel(logging.INFO if verbose_access else logging.WARNING)
    access = logging.getLogger("uvicorn.access")
    for f in list(access.filters):
        if isinstance(f, QuietAccessFilter):
            access.removeFilter(f)
    if not verbose_access:
        access.addFilter(QuietAccessFilter())
