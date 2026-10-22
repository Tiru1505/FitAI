import logging
import re

_SENSITIVE = re.compile(r"(token=|password[\"']?\s*[:=]\s*)[^\s&\"',}]+", re.IGNORECASE)


class RedactSensitiveFilter(logging.Filter):
    """Redacts tokens and passwords if they ever reach a log message."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = _SENSITIVE.sub(r"\1[REDACTED]", record.msg)
        if record.args:
            record.args = tuple(
                _SENSITIVE.sub(r"\1[REDACTED]", a) if isinstance(a, str) else a for a in record.args
            )
        return True


def configure_logging(level: str) -> None:
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)s [%(name)s] %(message)s")
    redact = RedactSensitiveFilter()
    for name in ("", "uvicorn.access", "uvicorn.error", "fitai"):
        logging.getLogger(name).addFilter(redact)
