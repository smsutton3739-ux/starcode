"""Language-model access, with a deterministic offline fallback.

Two providers behind one interface:

* :class:`AnthropicProvider` — the real thing, used when ``ANTHROPIC_API_KEY`` is set.
* :class:`OfflineProvider` — a deterministic rule-based engine. Not a stub that returns
  empty results: it does real work with the corpus, calendars and ephemeris, so the whole
  platform is demonstrable, testable and CI-runnable with no credentials and no network.

The offline provider is *labelled as such* everywhere it appears. Its output is honest
about being pattern-based, and the report says which provider produced it. A user must
never be unable to tell whether they were reading model output or rule output.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from typing import Any, Protocol

from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class ProviderError(RuntimeError):
    """A call failed in a way worth retrying."""


class ProviderUnavailable(RuntimeError):
    """The provider cannot be used at all (missing key, missing package)."""


@dataclass(slots=True)
class LLMResponse:
    text: str
    provider: str
    model: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    stop_reason: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    def json(self) -> Any:
        """Parse the response as JSON, tolerating the ways models wrap it.

        Models fence JSON in markdown, prepend commentary, or append a closing remark.
        Rather than fail the whole agent on presentation, extract the first balanced
        JSON value and parse that.
        """
        return extract_json(self.text)


def extract_json(text: str) -> Any:
    """Pull the first JSON object or array out of a string."""
    if not text or not text.strip():
        raise ValueError("empty response")

    stripped = text.strip()
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass

    fence = re.search(r"```(?:json)?\s*(.+?)```", stripped, re.DOTALL)
    if fence:
        try:
            return json.loads(fence.group(1).strip())
        except json.JSONDecodeError:
            stripped = fence.group(1).strip()

    for opener, closer in (("{", "}"), ("[", "]")):
        start = stripped.find(opener)
        if start == -1:
            continue
        depth = 0
        in_string = False
        escaped = False
        for index in range(start, len(stripped)):
            char = stripped[index]
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
                continue
            if char == '"':
                in_string = True
            elif char == opener:
                depth += 1
            elif char == closer:
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(stripped[start : index + 1])
                    except json.JSONDecodeError:
                        break

    raise ValueError(f"no parseable JSON in response (first 200 chars: {text[:200]!r})")


class LLMProvider(Protocol):
    name: str
    model: str

    def complete(
        self,
        system: str,
        prompt: str,
        *,
        max_tokens: int | None = None,
        temperature: float | None = None,
        prefill: str | None = None,
    ) -> LLMResponse: ...


# --------------------------------------------------------------------------------------
# Anthropic
# --------------------------------------------------------------------------------------


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, model: str | None = None, api_key: str | None = None) -> None:
        try:
            import anthropic
        except ImportError as exc:  # pragma: no cover - package is a hard dependency
            raise ProviderUnavailable("anthropic package is not installed") from exc

        key = api_key or settings.ANTHROPIC_API_KEY
        if not key:
            raise ProviderUnavailable("ANTHROPIC_API_KEY is not set")

        self.model = model or settings.AI_MODEL
        self._client = anthropic.Anthropic(api_key=key, timeout=settings.AI_TIMEOUT_SECONDS)
        self._anthropic = anthropic

    @retry(
        retry=retry_if_exception_type(ProviderError),
        stop=stop_after_attempt(settings.AI_MAX_RETRIES),
        wait=wait_exponential(multiplier=1, min=1, max=20),
        reraise=True,
    )
    def complete(
        self,
        system: str,
        prompt: str,
        *,
        max_tokens: int | None = None,
        temperature: float | None = None,
        prefill: str | None = None,
    ) -> LLMResponse:
        messages: list[dict] = [{"role": "user", "content": prompt}]
        if prefill:
            # Prefilling the assistant turn is the reliable way to force JSON-only output.
            messages.append({"role": "assistant", "content": prefill})

        try:
            response = self._client.messages.create(
                model=self.model,
                system=system,
                messages=messages,
                max_tokens=max_tokens or settings.AI_MAX_TOKENS,
                temperature=(temperature if temperature is not None else settings.AI_TEMPERATURE),
            )
        except self._anthropic.APIStatusError as exc:
            # 4xx other than 429 are our fault and will not fix themselves on retry.
            if exc.status_code == 429 or exc.status_code >= 500:
                raise ProviderError(f"Anthropic API {exc.status_code}: {exc}") from exc
            raise
        except (self._anthropic.APIConnectionError, self._anthropic.APITimeoutError) as exc:
            raise ProviderError(f"Anthropic connection failure: {exc}") from exc

        text = "".join(block.text for block in response.content if block.type == "text")
        if prefill:
            text = prefill + text

        return LLMResponse(
            text=text,
            provider=self.name,
            model=self.model,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            stop_reason=response.stop_reason,
        )


# --------------------------------------------------------------------------------------
# Offline
# --------------------------------------------------------------------------------------


class OfflineProvider:
    """Deterministic engine used when no API key is configured.

    It answers the *structured* questions agents ask by pattern matching against the
    lexicons in `app.agents.lexicon` and the platform's own calendar/astronomy engines.
    It cannot do open-ended reasoning, and it does not pretend to: agents that need
    genuine synthesis (alternative interpretations, executive prose) receive an explicit
    ``offline_unavailable`` marker and degrade to reporting only what the deterministic
    engines found.

    This is what makes the repository runnable by anyone who clones it.
    """

    name = "offline"
    model = "starcode-deterministic-v1"

    def complete(
        self,
        system: str,
        prompt: str,
        *,
        max_tokens: int | None = None,
        temperature: float | None = None,
        prefill: str | None = None,
    ) -> LLMResponse:
        from app.agents import offline_engine

        task = _detect_task(system, prompt)
        payload = offline_engine.handle(task, prompt)
        return LLMResponse(
            text=json.dumps(payload),
            provider=self.name,
            model=self.model,
            input_tokens=len(prompt) // 4,
            output_tokens=0,
            stop_reason="end_turn",
            raw={"task": task},
        )


_TASK_MARKER = re.compile(r"<task>\s*([a-z_]+)\s*</task>")


def _detect_task(system: str, prompt: str) -> str:
    """Agents tag their prompts with `<task>name</task>` so the offline engine can route.

    The tag is inert for a real model — it reads as ordinary structure — and load-bearing
    for the offline path, which keeps a single prompt working for both providers.
    """
    for text in (prompt, system):
        match = _TASK_MARKER.search(text)
        if match:
            return match.group(1)
    return "unknown"


# --------------------------------------------------------------------------------------
# Selection
# --------------------------------------------------------------------------------------

_provider: LLMProvider | None = None


def get_provider(force: str | None = None) -> LLMProvider:
    """Return the active provider, constructing it on first use."""
    global _provider

    choice = force or settings.AI_PROVIDER
    if force is None and _provider is not None:
        return _provider

    provider: LLMProvider
    if choice == "offline":
        provider = OfflineProvider()
    elif choice == "anthropic":
        provider = AnthropicProvider()
    else:  # auto
        if settings.use_anthropic:
            try:
                provider = AnthropicProvider()
            except ProviderUnavailable as exc:
                logger.warning("provider.anthropic_unavailable", reason=str(exc))
                provider = OfflineProvider()
        else:
            provider = OfflineProvider()

    if force is None:
        _provider = provider
        logger.info("provider.selected", provider=provider.name, model=provider.model)
    return provider


def set_provider(provider: LLMProvider | None) -> None:
    """Override the provider (tests, admin model switching)."""
    global _provider
    _provider = provider


def provider_status() -> dict:
    provider = get_provider()
    return {
        "provider": provider.name,
        "model": provider.model,
        "is_offline": provider.name == "offline",
        "note": (
            "Running the deterministic offline engine: results come from rule-based "
            "pattern matching plus the calendar and astronomy engines, not from a language "
            "model. Interpretive sections will be sparse. Set ANTHROPIC_API_KEY for full "
            "analysis."
            if provider.name == "offline"
            else "Language-model analysis is active."
        ),
    }


def timed_complete(
    provider: LLMProvider, system: str, prompt: str, **kwargs: Any
) -> tuple[LLMResponse, int]:
    start = time.perf_counter()
    response = provider.complete(system, prompt, **kwargs)
    return response, int((time.perf_counter() - start) * 1000)


__all__ = [
    "LLMProvider",
    "LLMResponse",
    "AnthropicProvider",
    "OfflineProvider",
    "ProviderError",
    "ProviderUnavailable",
    "get_provider",
    "set_provider",
    "provider_status",
    "extract_json",
    "timed_complete",
]
