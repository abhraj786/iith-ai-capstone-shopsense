"""Provider-agnostic structured-output LLM client built on LiteLLM (M1).

The model is chosen by configuration (`CAPSTONE_LLM_MODEL`), e.g. "gemini/gemini-flash-latest"
or "openai/gpt-4o-mini"; no code here names a provider. `completion` is injectable so tests
run offline with a fake.
"""

import json
import logging
import time
from typing import Callable, TypeVar

from pydantic import BaseModel, ValidationError

from capstone.settings import Settings, get_settings

T = TypeVar("T", bound=BaseModel)

logging.getLogger("LiteLLM").setLevel(logging.ERROR)  # per-call deprecation chatter


class LLMError(Exception):
    """The model call failed or never produced output matching the schema."""


class LLMClient:
    def __init__(self, settings: Settings | None = None, completion: Callable | None = None):
        self.settings = settings or get_settings()
        if completion is None:
            import litellm  # imported lazily so offline tests don't need provider setup
            completion = litellm.completion
        self._completion = completion
        self.usage = {"calls": 0, "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0}

    def structured(self, system: str, user: str, schema: type[T]) -> T:
        """Ask the model for JSON matching `schema`; on invalid output retry with the error."""
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        last_error, content = "", ""
        for _ in range(self.settings.llm_max_retries + 1):
            try:
                response = self._call(messages, schema)
                self._record_usage(response)
                content = response.choices[0].message.content
                return schema.model_validate_json(content)
            except (ValidationError, json.JSONDecodeError, TypeError) as e:
                last_error = str(e)
                messages = messages[:2] + [
                    {"role": "assistant", "content": content},
                    {"role": "user", "content": f"That was not valid for the schema: {last_error[:500]}. "
                                                "Return corrected JSON only."},
                ]
            except Exception as e:  # provider/network failure after our own retries
                raise LLMError(f"{type(e).__name__}: {e}") from e
        raise LLMError(f"No schema-valid output after retries: {last_error[:300]}")

    def _call(self, messages: list[dict], schema: type[BaseModel]):
        """One provider call. Rate limits (429) wait and retry with doubling delay."""
        delay = self.settings.llm_rate_limit_backoff_s
        for attempt in range(self.settings.llm_rate_limit_retries + 1):
            try:
                return self._completion(
                    model=self.settings.llm_model, messages=messages, temperature=0,
                    response_format=schema, timeout=self.settings.llm_timeout_s, num_retries=2,
                )
            except Exception as e:
                if type(e).__name__ != "RateLimitError" or attempt == self.settings.llm_rate_limit_retries:
                    raise
                time.sleep(delay)
                delay *= 2

    def _record_usage(self, response) -> None:
        """Add this call's tokens (and a best-effort price) to the running totals."""
        usage = getattr(response, "usage", None)
        self.usage["calls"] += 1
        if usage is None:
            return
        self.usage["input_tokens"] += int(getattr(usage, "prompt_tokens", 0) or 0)
        self.usage["output_tokens"] += int(getattr(usage, "completion_tokens", 0) or 0)
        try:
            import litellm
            self.usage["cost_usd"] += float(litellm.completion_cost(completion_response=response) or 0.0)
        except Exception:  # unknown model price: tokens still count
            pass

    def usage_since(self, before: dict) -> dict:
        return {k: round(self.usage[k] - before[k], 8) if k == "cost_usd" else self.usage[k] - before[k]
                for k in self.usage}
