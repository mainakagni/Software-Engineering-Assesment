"""JSON logs on stdout, one object per line.

The request ID lives in a context variable so every log line written while handling a request
(or while the worker processes a job started by that request) carries it without passing it around.
"""

import json
import logging
from contextvars import ContextVar
from datetime import UTC, datetime

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)
user_id_var: ContextVar[str | None] = ContextVar("user_id", default=None)

# Attributes every LogRecord has. Anything else on a record came in through `extra=` and is
# written out as its own field (except uvicorn's ANSI-coloured copy of the message).
_SKIPPED_ATTRS = frozenset(vars(logging.LogRecord("", 0, "", 0, "", None, None))) | {
    "message",
    "color_message",
}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, object] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
        }
        if request_id := request_id_var.get():
            entry["request_id"] = request_id
        if user_id := user_id_var.get():
            entry["user_id"] = user_id
        entry.update({k: v for k, v in vars(record).items() if k not in _SKIPPED_ATTRS})
        if record.exc_info:
            entry["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(entry, default=str)


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())

    # uvicorn installs its own handlers; route its messages through ours instead, and drop its
    # access log because the request middleware writes a richer one.
    for name in ("uvicorn", "uvicorn.error"):
        uvicorn_logger = logging.getLogger(name)
        uvicorn_logger.handlers = []
        uvicorn_logger.propagate = True
    logging.getLogger("uvicorn.access").disabled = True
