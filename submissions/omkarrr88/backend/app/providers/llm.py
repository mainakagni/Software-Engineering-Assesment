"""Answer generation: the interface the app uses, and the Gemini implementation."""

from dataclasses import dataclass
from typing import Any, Protocol

from google import genai
from google.genai import types

from app.providers.errors import ProviderError
from app.providers.gemini import PROVIDER, translate_error

# The model stopped for a reason that asking again will not change.
_BLOCKED = frozenset({"SAFETY", "RECITATION", "BLOCKLIST", "PROHIBITED_CONTENT", "SPII"})


@dataclass(frozen=True)
class LLMResult:
    text: str
    prompt_tokens: int
    output_tokens: int
    thinking_tokens: int
    model: str


class LLMClient(Protocol):
    model: str

    def generate_json(self, system: str, user: str, schema: dict[str, Any]) -> LLMResult:
        """One reply constrained to `schema`. Raises ProviderError; retrying is the caller's job."""
        ...


class GeminiLLM:
    def __init__(
        self,
        client: genai.Client,
        *,
        model: str,
        temperature: float,
        max_output_tokens: int,
        thinking_level: str,
    ) -> None:
        self.client = client
        self.model = model
        self.temperature = temperature
        self.max_output_tokens = max_output_tokens
        self.thinking_level = thinking_level

    def generate_json(self, system: str, user: str, schema: dict[str, Any]) -> LLMResult:
        config = types.GenerateContentConfig(
            system_instruction=system,
            temperature=self.temperature,
            max_output_tokens=self.max_output_tokens,
            response_mime_type="application/json",
            response_json_schema=schema,
            # No tools are sent, so skip the SDK's function-calling loop (and its log warning).
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        )
        if self.thinking_level:
            config.thinking_config = types.ThinkingConfig(
                thinking_level=types.ThinkingLevel(self.thinking_level)
            )
        try:
            response = self.client.models.generate_content(
                model=self.model, contents=user, config=config
            )
        except Exception as exc:
            raise translate_error(exc) from exc
        return self._result(response)

    def _result(self, response: types.GenerateContentResponse) -> LLMResult:
        finish = response.candidates[0].finish_reason if response.candidates else None
        finish_name = finish.name if finish is not None else "none"
        if finish_name in _BLOCKED:
            raise ProviderError(
                PROVIDER, "bad_request", f"The reply was blocked ({finish_name}).", retryable=False
            )
        if not response.text:
            raise ProviderError(
                PROVIDER, "bad_response", f"Empty reply (finish: {finish_name}).", retryable=True
            )
        usage = response.usage_metadata
        return LLMResult(
            text=response.text,
            prompt_tokens=(usage.prompt_token_count or 0) if usage else 0,
            output_tokens=(usage.candidates_token_count or 0) if usage else 0,
            thinking_tokens=(usage.thoughts_token_count or 0) if usage else 0,
            model=self.model,
        )
