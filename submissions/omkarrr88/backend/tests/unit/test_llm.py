"""The Gemini answer model (with a stand-in client) and the offline FakeLLM."""

import json
from types import SimpleNamespace
from typing import Any

import pytest
from google.genai import errors

from app.providers.errors import ProviderError
from app.providers.fakes import FakeLLM
from app.providers.llm import GeminiLLM
from app.qa.prompt import ANSWER_SCHEMA, SYSTEM_PROMPT, build_user_prompt
from tests.qa_factory import make_chunk

# --- Gemini, with a stand-in client --------------------------------------------------------------


class _Models:
    def __init__(self, response: Any = None, error: Exception | None = None) -> None:
        self.response, self.error = response, error
        self.requests: list[dict[str, Any]] = []

    def generate_content(self, *, model: str, contents: str, config: Any) -> Any:
        self.requests.append({"model": model, "contents": contents, "config": config})
        if self.error:
            raise self.error
        return self.response


def _response(text: str | None, finish: str = "STOP") -> Any:
    usage = SimpleNamespace(
        prompt_token_count=900, candidates_token_count=80, thoughts_token_count=40
    )
    candidate = SimpleNamespace(finish_reason=SimpleNamespace(name=finish))
    return SimpleNamespace(text=text, candidates=[candidate], usage_metadata=usage)


def _llm(models: _Models, thinking_level: str = "LOW") -> GeminiLLM:
    return GeminiLLM(
        SimpleNamespace(models=models),  # type: ignore[arg-type]
        model="gemini-test",
        temperature=0.1,
        max_output_tokens=512,
        thinking_level=thinking_level,
    )


def test_gemini_request_and_usage() -> None:
    models = _Models(_response('{"found": false, "citations": [], "answer": "No."}'))
    result = _llm(models).generate_json("system rules", "user prompt", ANSWER_SCHEMA)
    [request] = models.requests
    config = request["config"]
    assert (request["model"], request["contents"]) == ("gemini-test", "user prompt")
    assert config.system_instruction == "system rules"
    assert config.response_mime_type == "application/json"
    assert config.response_json_schema == ANSWER_SCHEMA
    assert config.thinking_config.thinking_level.value == "LOW"
    assert config.automatic_function_calling.disable is True
    assert (result.prompt_tokens, result.output_tokens, result.thinking_tokens) == (900, 80, 40)


def test_thinking_config_can_be_left_out() -> None:
    models = _Models(_response('{"found": false, "citations": [], "answer": "No."}'))
    _llm(models, thinking_level="").generate_json("s", "u", ANSWER_SCHEMA)
    assert models.requests[0]["config"].thinking_config is None


def test_blocked_and_empty_replies() -> None:
    with pytest.raises(ProviderError) as blocked:
        _llm(_Models(_response(None, finish="SAFETY"))).generate_json("s", "u", ANSWER_SCHEMA)
    assert (blocked.value.kind, blocked.value.retryable) == ("bad_request", False)

    with pytest.raises(ProviderError) as empty:
        _llm(_Models(_response("", finish="MAX_TOKENS"))).generate_json("s", "u", ANSWER_SCHEMA)
    assert (empty.value.kind, empty.value.retryable) == ("bad_response", True)


def test_sdk_errors_become_provider_errors() -> None:
    error = errors.APIError(
        503, {"error": {"code": 503, "message": "overloaded", "status": "UNAVAILABLE"}}
    )
    with pytest.raises(ProviderError) as caught:
        _llm(_Models(error=error)).generate_json("s", "u", ANSWER_SCHEMA)
    assert (caught.value.kind, caught.value.retryable) == ("unavailable", True)


# --- fake LLM ------------------------------------------------------------------------------------


def test_fake_llm_answers_from_the_best_matching_sentence() -> None:
    prompt, _ = build_user_prompt("How early must international flights be booked?", [make_chunk()])
    reply = json.loads(FakeLLM().generate_json(SYSTEM_PROMPT, prompt, ANSWER_SCHEMA).text)
    assert reply["found"] is True
    assert reply["citations"] == [
        {
            "source_id": "S1",
            "quote": "International flights must be booked at least 14 business days in advance.",
        }
    ]


def test_fake_llm_says_not_found_without_overlap_and_replays_queued_replies() -> None:
    fake = FakeLLM()
    prompt, _ = build_user_prompt("Who founded the company?", [make_chunk()])
    assert json.loads(fake.generate_json("s", prompt, ANSWER_SCHEMA).text)["found"] is False

    fake.queue("scripted", ProviderError("fake", "timeout", "slow", retryable=True))
    assert fake.generate_json("s", prompt, ANSWER_SCHEMA).text == "scripted"
    with pytest.raises(ProviderError):
        fake.generate_json("s", prompt, ANSWER_SCHEMA)
    assert len(fake.calls) == 3
