"""
Everything that talks to the NVIDIA AI service lives here, in one place.

Before, the model names and the connection were copy-pasted into three files,
so changing a model meant remembering to edit all three. Now you change it once
here (or in your .env file).
"""
import os
import json
import random
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dotenv import load_dotenv
import openai
from openai import OpenAI

load_dotenv()

CHAT_MODEL = os.getenv("CHAT_MODEL", "nvidia/nemotron-3-super-120b-a12b")
EMBED_MODEL = os.getenv("EMBED_MODEL", "nvidia/nemotron-3-embed-1b")
EMBED_BATCH_SIZE = 32  # how many facts to turn into vectors in one request

# How many requests may be in flight to NVIDIA at the same time, IN TOTAL across the whole
# app (default 4). Higher is faster; if NVIDIA keeps refusing requests with
# "429 Too Many Requests", lower it in .env.
MAX_PARALLEL_AI_CALLS = max(1, int(os.getenv("MAX_PARALLEL_AI_CALLS", "4")))

# Cap on requests per minute (default 30; 0 = no cap). NVIDIA's free tier limits how many
# requests an account may make in a period; going over gets every request refused with
# "429 Too Many Requests" for a while. Pacing requests keeps us under the limit.
# Raise it if your NVIDIA plan allows more.
MAX_REQUESTS_PER_MINUTE = max(0, int(os.getenv("MAX_REQUESTS_PER_MINUTE", "30")))

# When NVIDIA says "too many requests", keep waiting (all requests pause together) for up
# to this many seconds before giving up. Other errors use RETRY_ATTEMPTS instead.
RATE_LIMIT_PATIENCE_SECONDS = max(0.0, float(os.getenv("AI_RATE_LIMIT_PATIENCE", "300")))
RATE_LIMIT_MAX_TRIES = 30   # safety stop, however the time is counted

# How many times to try a request before giving up.
RETRY_ATTEMPTS = max(1, int(os.getenv("AI_RETRY_ATTEMPTS", "6")))

# A missing key must not crash the app on start-up (then even /health would fail). The
# first AI request reports it clearly instead (see _permanent_problem).
API_KEY = os.getenv("NVIDIA_API_KEY", "").strip()
AI_CONFIGURED = bool(API_KEY) and API_KEY != "your_key_here"

client = OpenAI(
    base_url=os.getenv("AI_BASE_URL", "https://integrate.api.nvidia.com/v1"),
    api_key=API_KEY or "missing-key",
)


def _pause(seconds: float) -> None:
    """Wait between retries (a separate function so tests can skip the waiting)."""
    time.sleep(seconds)


class AIServiceError(Exception):
    """Raised when the AI service keeps failing even after retrying."""


class ContextTooLongError(AIServiceError):
    """The prompt was bigger than the model accepts. The caller should split it and retry."""


def _is_context_too_long(error: Exception) -> bool:
    text = str(error).lower()
    return isinstance(error, openai.BadRequestError) and any(
        k in text for k in ("context length", "context_length", "maximum context", "too long",
                            "too many tokens", "prompt is too long", "max_tokens"))


# ---------------------------------------------------------------------------
# One gate for every request to NVIDIA
# ---------------------------------------------------------------------------
# Several parts of the app run work in parallel (passages, checks, the safety net),
# sometimes inside each other. Each part limiting itself isn't enough: the TOTAL number
# of requests in flight could exceed MAX_PARALLEL_AI_CALLS. This single gate is what
# actually enforces the limit, however the work is arranged.
_slots = threading.BoundedSemaphore(MAX_PARALLEL_AI_CALLS)

# Pacing that learns. Requests are spaced evenly (not sent in bursts) at a rate that starts
# at MAX_REQUESTS_PER_MINUTE. Each "too many requests" refusal halves the rate (never below
# MIN_REQUESTS_PER_MINUTE); every 10 accepted requests raise it by one again, up to the maximum.
# So StoryForge settles just under whatever limit NVIDIA is applying right now.
MIN_REQUESTS_PER_MINUTE = 4
_rate_lock = threading.Lock()
_current_rpm: float | None = None      # None = start at MAX_REQUESTS_PER_MINUTE
_next_start = 0.0
_accepted_since_change = 0


def _effective_rpm() -> float:
    maximum = float(MAX_REQUESTS_PER_MINUTE)
    return min(maximum, _current_rpm) if _current_rpm is not None else maximum


def _wait_for_rate_limit() -> None:
    """Space requests evenly at the current learned rate."""
    global _next_start
    if not MAX_REQUESTS_PER_MINUTE:
        return
    with _rate_lock:
        now = time.monotonic()
        start = max(now, _next_start)
        _next_start = start + 60.0 / _effective_rpm()
    if start > now:
        time.sleep(start - now)


def _slow_down() -> None:
    """NVIDIA refused a request: halve the pace."""
    global _current_rpm, _accepted_since_change
    if not MAX_REQUESTS_PER_MINUTE:
        return
    with _rate_lock:
        before = _effective_rpm()
        _current_rpm = max(float(MIN_REQUESTS_PER_MINUTE), before / 2)
        _accepted_since_change = 0
        after = _current_rpm
    if after < before:
        print(f"  [pacing] NVIDIA is limiting requests; slowing to {after:.0f} per minute", flush=True)


def _speed_up_gradually() -> None:
    """A request was accepted: after 10 in a row, allow one more per minute."""
    global _current_rpm, _accepted_since_change
    if not MAX_REQUESTS_PER_MINUTE or _current_rpm is None:
        return
    with _rate_lock:
        _accepted_since_change += 1
        if _accepted_since_change >= 10:
            _accepted_since_change = 0
            _current_rpm = min(float(MAX_REQUESTS_PER_MINUTE), _current_rpm + 1)


# Shared pause after a "too many requests" refusal: every request waits it out, instead
# of each one retrying on its own and keeping the limit exceeded.
_cooldown_lock = threading.Lock()
_cooldown_until = 0.0
_refusals_in_a_row = 0
request_count = 0          # requests sent to NVIDIA, including refused ones (for reports)
refused_count = 0          # of those, how many NVIDIA refused with "too many requests"


def _is_rate_limited(error: Exception) -> bool:
    return isinstance(error, openai.RateLimitError) or getattr(error, "status_code", None) == 429


def _start_cooldown(error: Exception) -> float:
    """Pause ALL requests: 10 s after one refusal, doubling for each refusal in a row, up to 2 min."""
    global _cooldown_until, _refusals_in_a_row
    with _cooldown_lock:
        _refusals_in_a_row += 1
        pause = min(120.0, 10.0 * (2 ** (_refusals_in_a_row - 1)))
        response = getattr(error, "response", None)
        try:
            pause = max(pause, float(response.headers.get("retry-after", 0)))
        except (TypeError, ValueError, AttributeError):
            pass
        _cooldown_until = max(_cooldown_until, time.monotonic() + pause)
        return pause


def _wait_for_cooldown() -> None:
    with _cooldown_lock:
        remaining = _cooldown_until - time.monotonic()
    if remaining > 0:
        _pause(remaining)


def _call_api(request):
    """Send one request to NVIDIA through the gate."""
    global request_count, refused_count, _refusals_in_a_row
    _wait_for_cooldown()
    _wait_for_rate_limit()
    with _slots:
        _wait_for_cooldown()          # a pause may have started while we waited for a slot
        with _cooldown_lock:
            request_count += 1
        try:
            result = request()
        except Exception as error:
            if _is_rate_limited(error):
                with _cooldown_lock:
                    refused_count += 1
                _slow_down()
            raise
    with _cooldown_lock:
        _refusals_in_a_row = 0        # NVIDIA accepted a request: back to normal
    _speed_up_gradually()
    return result


# Errors that can never succeed on a retry: stop at once with a clear message.
def _permanent_problem(error: Exception) -> str | None:
    if not AI_CONFIGURED and isinstance(error, (openai.AuthenticationError, openai.PermissionDeniedError)):
        return "No NVIDIA_API_KEY is set. Add it to backend/.env (or the host's environment settings)."
    if isinstance(error, openai.AuthenticationError) or isinstance(error, openai.PermissionDeniedError):
        return "NVIDIA rejected the API key. Check NVIDIA_API_KEY in backend/.env."
    if isinstance(error, openai.NotFoundError):
        return ("NVIDIA doesn't recognise the model name; it may have been retired. "
                "Set CHAT_MODEL / EMBED_MODEL in backend/.env to a current model.")
    if isinstance(error, openai.BadRequestError):
        return f"NVIDIA refused the request as invalid: {str(error)[:200]}"
    return None


def _retry_wait(error: Exception, attempt: int) -> float:
    """
    How long to wait before the next try: 2, 4, 8, 16, 32... seconds (up to 60), plus a
    little randomness so parallel requests don't all retry at the same instant. If NVIDIA
    says how long to wait (a Retry-After header on a 429), wait at least that long.
    """
    wait = min(60.0, 2.0 * (2 ** (attempt - 1)))
    response = getattr(error, "response", None)
    if response is not None:
        try:
            wait = max(wait, float(response.headers.get("retry-after", 0)))
        except (TypeError, ValueError, AttributeError):
            pass
    return wait + random.uniform(0, 1.5)


def with_retries(action, what: str, attempts: int | None = None):
    """
    Try `action` until it works:
    - "Too many requests" (429): all requests pause together (see _start_cooldown), and we
      keep trying for up to AI_RATE_LIMIT_PATIENCE seconds (default 5 minutes).
    - Other temporary failures (overloaded server, garbled answer): up to `attempts` tries
      (default AI_RETRY_ATTEMPTS, 6), waiting longer after each.
    - Problems that can never succeed (bad API key, unknown model) stop at once.
    """
    attempts = attempts or RETRY_ATTEMPTS
    failures = 0
    refusals = 0
    refused_since = None
    last_error = None
    while True:
        try:
            return action()
        except Exception as error:
            if _is_context_too_long(error):
                raise ContextTooLongError(f"{what} failed: the request was too long for the model.") from error
            problem = _permanent_problem(error)
            if problem:
                raise AIServiceError(f"{what} failed: {problem}") from error
            last_error = error
            if _is_rate_limited(error):
                refusals += 1
                refused_since = refused_since or time.monotonic()
                waited = time.monotonic() - refused_since
                if waited >= RATE_LIMIT_PATIENCE_SECONDS or refusals >= RATE_LIMIT_MAX_TRIES:
                    raise AIServiceError(
                        f"{what} failed: NVIDIA kept refusing with 'Too Many Requests' for "
                        f"{waited / 60:.0f} minutes. Your NVIDIA usage limit is probably used up for "
                        f"now. Wait a while and try again, or lower MAX_REQUESTS_PER_MINUTE in backend/.env."
                    ) from error
                pause = _start_cooldown(error)
                print(f"  [waiting] {what}: NVIDIA says too many requests; all requests pause "
                      f"{pause:.0f}s (waited {waited:.0f}s so far)", flush=True)
                _wait_for_cooldown()
                continue
            failures += 1
            if failures >= attempts:
                break
            wait = _retry_wait(error, failures)
            print(f"  [retry] {what}: attempt {failures} failed ({str(error)[:120]}); "
                  f"trying again in {wait:.0f}s", flush=True)
            _pause(wait)
    raise AIServiceError(f"{what} failed after {attempts} tries: {last_error}") from last_error


# How much the model "thinks" before answering, for all AI calls:
#   off  – answer directly. Fastest, and the most reliable at producing structured answers.
#   low  – a short think first. A middle ground.
#   on   – full thinking. Much slower; mainly useful for comparison.
# Set CHAT_THINKING in .env to change it.
#
# CHAT_THINKING          – reading facts from chapters and the Ask box (default: off).
#                          This is the slow, high-volume step, so thinking stays off.
# CHAT_THINKING_JUDGING  – linking names and checking for mistakes (default: low).
#                          These are judgement calls on short inputs, where a short
#                          think improves accuracy for little extra time.
def _mode(variable: str, default: str) -> str:
    value = os.getenv(variable, default).strip().lower()
    return value if value in ("off", "low", "on") else default


THINKING_MODE = _mode("CHAT_THINKING", "off")
if os.getenv("CHAT_DISABLE_THINKING", "").lower() == "true":   # older setting name
    THINKING_MODE = "off"
JUDGING_THINKING_MODE = _mode("CHAT_THINKING_JUDGING", "low")
DISABLE_THINKING = THINKING_MODE == "off"
_unsupported_modes: set[str] = set()   # modes the service rejected; we fall back to "off"


def _thinking_options(mode: str | None = None) -> dict:
    mode = mode or THINKING_MODE
    if mode in _unsupported_modes:
        mode = "off"
    kwargs = {"off": {"enable_thinking": False},
              "low": {"enable_thinking": True, "low_effort": True},
              "on": {"enable_thinking": True}}[mode]
    return {"extra_body": {"chat_template_kwargs": kwargs}}


MAX_TOKENS_CEILING = 16384

# Randomness of the AI's answers (0 = always the same answer, 1 = varied).
# Kept low so the same chapter gives the same result from run to run.
TEMPERATURE = float(os.getenv("CHAT_TEMPERATURE", "0.2"))


def _json_from_text(text: str | None) -> dict:
    """
    Pull a JSON object out of a plain-text answer. Handles <think>...</think> notes,
    ```json fences, and text written before or after the JSON.
    """
    text = re.sub(r"<think>.*?</think>", "", text or "", flags=re.S)
    text = re.sub(r"```(?:json)?", "", text)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("no JSON object in the text answer")
    data = json.loads(text[start:end + 1])
    # Some models write the tool call itself as text: {"name": ..., "arguments": {...}}
    inner = data.get("arguments", data.get("parameters")) if isinstance(data, dict) else None
    if inner is not None and "name" in data:
        data = json.loads(inner) if isinstance(inner, str) else inner
    if not isinstance(data, dict):
        raise ValueError("the text answer was not a JSON object")
    return data


def call_tool(prompt: str, tool: dict, max_tokens: int = 4096, thinking: str | None = None) -> dict:
    """
    Ask the chat model a question and force it to answer in the structured
    format described by `tool`. Returns the answer as a Python dict.

    If the model answers in plain text instead, the JSON is taken from the text.
    If it ran out of space, the next try gets twice as much room.
    thinking: "off" / "low" / "on" for this call (default: CHAT_THINKING).
    """
    tool_name = tool["function"]["name"]
    # The answer space only grows after an answer was actually CUT OFF (finish_reason
    # "length"). Refusals, outages and garbled answers retry with the same budget.
    state = {"budget": min(max_tokens, MAX_TOKENS_CEILING)}

    def ask_once():
        budget = state["budget"]
        request = dict(
            model=CHAT_MODEL,
            max_tokens=budget,
            temperature=TEMPERATURE,
            tools=[tool],
            tool_choice={"type": "function", "function": {"name": tool_name}},
            messages=[{"role": "user", "content": prompt}],
        )
        mode = thinking or THINKING_MODE
        try:
            response = _call_api(lambda: client.chat.completions.create(**request, **_thinking_options(mode)))
        except openai.BadRequestError as error:
            if mode == "off" or mode in _unsupported_modes or _is_context_too_long(error):
                raise
            # Maybe the service doesn't support this thinking setting. Try "off": only if THAT
            # works is the setting remembered as unsupported. (Before, any rejected request,
            # e.g. one that was simply too long, switched thinking off for good.)
            response = _call_api(lambda: client.chat.completions.create(**request, **_thinking_options("off")))
            print(f"  [note] thinking mode '{mode}' was rejected by the AI service; using 'off' instead", flush=True)
            _unsupported_modes.add(mode)
        choice = response.choices[0]
        if getattr(choice, "finish_reason", None) == "length":
            state["budget"] = min(budget * 2, MAX_TOKENS_CEILING)
        message = choice.message
        if message.tool_calls:
            # If the answer was cut off or garbled, this raises and we retry.
            return json.loads(message.tool_calls[0].function.arguments)
        # Fallback: the model wrote its answer as plain text instead.
        try:
            return _json_from_text(message.content)
        except ValueError:
            finish = getattr(choice, "finish_reason", None)
            hint = " (it ran out of space)" if finish == "length" else ""
            preview = " ".join((message.content or "").split())[:160]
            raise ValueError(
                f"the model did not return a structured answer{hint}; "
                f"finish_reason={finish}, text began: {preview!r}"
            )

    return with_retries(ask_once, what=f"AI call '{tool_name}'")


def embed_texts(texts: list[str], input_type: str = "passage") -> list[list[float]]:
    """
    Turn many pieces of text into vectors (lists of numbers that capture meaning),
    sending them in batches instead of one request per text.

    input_type must be "passage" for text you STORE and "query" for text you
    SEARCH WITH. Mixing them up silently makes search worse.
    """
    vectors: list[list[float]] = []
    for start in range(0, len(texts), EMBED_BATCH_SIZE):
        batch = texts[start:start + EMBED_BATCH_SIZE]
        response = with_retries(
            lambda: _call_api(lambda: client.embeddings.create(
                input=batch,
                model=EMBED_MODEL,
                extra_body={"input_type": input_type, "truncate": "END"},
            )),
            what="Embedding request",
        )
        # Put results back in the same order as the input, just in case.
        for item in sorted(response.data, key=lambda d: d.index):
            vectors.append(item.embedding)
    return vectors


def ask_text(prompt: str, max_tokens: int = 1024) -> str:
    """Ask the chat model for a plain written answer (used by the "Ask" box)."""
    def ask_once():
        response = _call_api(lambda: client.chat.completions.create(
            model=CHAT_MODEL,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
            **_thinking_options(),
        ))
        text = response.choices[0].message.content or ""
        # Some models include their private reasoning in <think> tags; hide it.
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()
        if not text:
            raise ValueError("the model returned an empty answer")
        return text

    return with_retries(ask_once, what="Answering the question")


def run_in_parallel(function, items: list) -> list:
    """
    Run function(item) for every item, up to MAX_PARALLEL_AI_CALLS at once,
    and return the results in the same order as the items.
    Waiting for the AI is most of the time, so doing several calls at once is
    much faster than one after another.
    """
    if len(items) <= 1 or MAX_PARALLEL_AI_CALLS == 1:
        return [function(item) for item in items]
    with ThreadPoolExecutor(max_workers=MAX_PARALLEL_AI_CALLS) as pool:
        return list(pool.map(function, items))
