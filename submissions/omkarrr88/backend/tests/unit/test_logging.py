import json
import logging
import sys
import uuid
from datetime import datetime, timedelta

from app.logging_config import JsonFormatter, request_id_var, user_id_var


def _record(msg: str = "something.happened", **extra: object) -> logging.LogRecord:
    record = logging.LogRecord("app.test", logging.INFO, __file__, 1, msg, None, None)
    for key, value in extra.items():
        setattr(record, key, value)
    return record


def test_one_json_object_with_utc_timestamp() -> None:
    entry = json.loads(JsonFormatter().format(_record()))
    assert entry["event"] == "something.happened"
    assert entry["level"] == "INFO"
    assert entry["logger"] == "app.test"
    assert datetime.fromisoformat(entry["ts"]).utcoffset() == timedelta(0)


def test_extra_fields_become_top_level_keys_and_are_serialisable() -> None:
    document_id = uuid.uuid4()
    entry = json.loads(JsonFormatter().format(_record(document_id=document_id, attempt=2)))
    assert entry["document_id"] == str(document_id)
    assert entry["attempt"] == 2
    assert "args" not in entry  # standard record attributes are not copied


def test_uvicorn_colour_message_is_dropped() -> None:
    entry = json.loads(JsonFormatter().format(_record(color_message="\x1b[36mhi\x1b[0m")))
    assert "color_message" not in entry


def test_request_and_user_ids_come_from_context() -> None:
    request_token = request_id_var.set("req-123")
    user_token = user_id_var.set("user-9")
    try:
        entry = json.loads(JsonFormatter().format(_record()))
    finally:
        request_id_var.reset(request_token)
        user_id_var.reset(user_token)
    assert entry["request_id"] == "req-123"
    assert entry["user_id"] == "user-9"


def test_exceptions_are_included() -> None:
    record = _record()
    try:
        raise ValueError("boom")
    except ValueError:
        record.exc_info = sys.exc_info()
    entry = json.loads(JsonFormatter().format(record))
    assert "ValueError: boom" in entry["exc_info"]
