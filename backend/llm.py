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
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from dotenv import load_dotenv
import openai
from openai import OpenAI

load_dotenv()

# ---------------------------------------------------------------------------
# Which models to use
# ---------------------------------------------------------------------------
# NVIDIA retires hosted models with little warning (llama-3.1-70b, llama-3.3-70b,
# nv-embedqa-e5-v5, and on 2026-10-03 nemotron-3-super-120b-a12b). So there are two JOBS,
# each with a list of models, best first:
#   READER (CHAT_MODEL)  - reads every passage into facts, works out chapter timing, answers
#                          the Ask box. Most of the requests, so it should be FAST.
#   JUDGE  (JUDGE_MODEL) - links names, checks for mistakes, the safety net, the double-check.
#                          Fewer, harder decisions, so it should be ACCURATE.
# If NVIDIA says a model is gone (404 / 410), it's never asked again and the next one in the
# list takes over; a model that keeps failing (server errors) is set aside for a while. When
# every judge is gone, the readers judge. /health shows what is in use.
#
# Chosen by measurement (docs/FINAL-CONFIGURATION.md): both judges on identical facts,
# Ultra 71% precision / 83% recall vs Lightning 40% / 33%.
# `python check_models.py` (backend/) tests what your key can use right now;
# `python ../eval/probe_models.py` compares candidates on StoryForge's real requests.
DEFAULT_CHAT_MODELS = "nvidia/nemotron-3.5-lightning-30b-a3b,nvidia/nemotron-3-nano-omni-30b-a3b-reasoning"
DEFAULT_JUDGE_MODELS = "nvidia/nemotron-3-ultra-550b-a55b,nvidia/nemotron-3.5-lightning-30b-a3b"


def _model_list(*values: str) -> list[str]:
    models: list[str] = []
    for value in values:
        models += [m.strip() for m in (value or "").split(",") if m.strip()]
    return list(dict.fromkeys(models))


def configured_models(env=os.environ) -> tuple[list[str], list[str]]:
    """
    (reader models, judge models) from the settings. Older setting names still work:
    CHAT_MODEL_READING / CHAT_MODEL_JUDGING go first in their list, CHAT_MODEL_FALLBACKS are
    added at the end of the reader list.
    """
    readers = _model_list(env.get("CHAT_MODEL_READING", ""), env.get("CHAT_MODEL", "") or DEFAULT_CHAT_MODELS,
                          env.get("CHAT_MODEL_FALLBACKS", ""))
    judges = _model_list(env.get("CHAT_MODEL_JUDGING", ""), env.get("JUDGE_MODEL", "") or DEFAULT_JUDGE_MODELS)
    return readers, judges


CHAT_MODELS, JUDGE_MODELS = configured_models()
CHAT_MODEL = CHAT_MODELS[0]          # the configured first choices, for reports
JUDGE_MODEL = (JUDGE_MODELS or CHAT_MODELS)[0]

EMBED_MODEL = os.getenv("EMBED_MODEL", "nvidia/nemotron-3-embed-1b")
EMBED_BATCH_SIZE = 32  # how many facts to turn into vectors in one request

# Give up on one request after this many seconds (default 180). The OpenAI library's default
# of 10 minutes meant a stalled connection could hang a chapter for 10 minutes per try.
REQUEST_TIMEOUT = max(10.0, float(os.getenv("AI_REQUEST_TIMEOUT", "180")))

# A model that fails this many times in a row (server errors, garbled answers) is set aside
# for SET_ASIDE_SECONDS and the next model takes over, instead of 6 tries over minutes.
# Only when there IS another model: with no alternative, it keeps the full patience.
# (12 Oct held-out run: Ultra answered two 500s in a row in chapter 3, was set aside for 10
# minutes, and the much weaker fallback judged the rest of the book. Ultra's 500s are brief, so
# it now gets 4 tries and is only set aside for 2 minutes.)
FAILOVER_AFTER = max(1, int(os.getenv("AI_FAILOVER_AFTER", "4")))
SET_ASIDE_SECONDS = float(os.getenv("AI_SET_ASIDE_SECONDS", "120"))
# When every judge is gone, may the readers judge? Yes for the app (better than nothing); the
# evaluation's --judges comparison switches it off so a judge is never scored on another
# model's answers.
JUDGE_FALLS_BACK_TO_READERS = True

# How many requests may be in flight to NVIDIA at the same time, IN TOTAL across the whole
# app (default 4). Higher is faster; if NVIDIA keeps refusing requests with
# "429 Too Many Requests", lower it in .env.
MAX_PARALLEL_AI_CALLS = max(1, int(os.getenv("MAX_PARALLEL_AI_CALLS", "4")))

# Cap on requests per minute (default 30; 0 = no cap). NVIDIA's free tier limits how many
# requests an account may make in a period; going over gets every request refused with
# "429 Too Many Requests" for a while. Pacing requests keeps us under the limit.
# Raise it if your NVIDIA plan allows more.
# A model served on your own computer (Ollama, LM Studio, vLLM...): AI_BASE_URL points at it,
# e.g. http://localhost:11434/v1 for Ollama. No key, no rate limit, no NVIDIA-only options.
AI_BASE_URL = os.getenv("AI_BASE_URL", "https://integrate.api.nvidia.com/v1").strip()
LOCAL_AI = (os.getenv("AI_PROVIDER", "").strip().lower() == "local"
            or any(h in AI_BASE_URL for h in ("localhost", "127.0.0.1", "0.0.0.0", "host.docker.internal", ":11434")))
MAX_REQUESTS_PER_MINUTE = max(0, int(os.getenv("MAX_REQUESTS_PER_MINUTE", "0" if LOCAL_AI else "30")))

# When NVIDIA says "too many requests", keep waiting (all requests pause together) for up
# to this many seconds before giving up. Other errors use RETRY_ATTEMPTS instead.
RATE_LIMIT_PATIENCE_SECONDS = max(0.0, float(os.getenv("AI_RATE_LIMIT_PATIENCE", "300")))
RATE_LIMIT_MAX_TRIES = 30   # safety stop, however the time is counted

# How many times to try a request before giving up.
RETRY_ATTEMPTS = max(1, int(os.getenv("AI_RETRY_ATTEMPTS", "6")))

# A missing key must not crash the app on start-up (then even /health would fail). The
# first AI request reports it clearly instead (see _permanent_problem).
NVIDIA_KEY = os.getenv("NVIDIA_API_KEY", "").strip()
API_KEY = os.getenv("AI_API_KEY", "").strip() or NVIDIA_KEY
AI_CONFIGURED = LOCAL_AI or (bool(API_KEY) and API_KEY != "your_key_here")

client = OpenAI(
    base_url=AI_BASE_URL,
    api_key=API_KEY or ("local" if LOCAL_AI else "missing-key"),
    timeout=REQUEST_TIMEOUT,
    # Retrying is done by with_retries below, which honours the shared pacing and cool-down.
    # The library's own hidden retries (2 by default) multiplied every try by 3 and ignored
    # the pacing, which made "Too Many Requests" worse.
    max_retries=0,
)


# Embeddings may come from a different server than the chat models: with a local Reader the
# vectors can stay on NVIDIA (EMBED_MODEL nvidia/...), or come from the local server too
# (EMBED_MODEL e.g. nomic-embed-text, then run reembed.py once). EMBED_BASE_URL overrides.
EMBED_BASE_URL = os.getenv("EMBED_BASE_URL", "").strip() or (
    "https://integrate.api.nvidia.com/v1" if LOCAL_AI and EMBED_MODEL.startswith("nvidia/") else AI_BASE_URL)
EMBED_IS_NVIDIA = "nvidia.com" in EMBED_BASE_URL
_separate_embed_client = None if EMBED_BASE_URL == AI_BASE_URL else OpenAI(
    base_url=EMBED_BASE_URL, api_key=(NVIDIA_KEY if EMBED_IS_NVIDIA else API_KEY) or "local",
    timeout=REQUEST_TIMEOUT, max_retries=0)


def _embed_client():
    """Looked up at call time, so the tests' fake client is used when it replaces `client`."""
    return _separate_embed_client or client


# ------------------------------------------------------------------ providers --
# Several free services can be chained: "ollama:qwen2.5:7b-instruct,groq:llama-3.3-70b-versatile,
# nvidia:nvidia/nemotron-3.5-lightning-30b-a3b". A model name WITHOUT a known provider in front
# uses AI_BASE_URL as before. Each provider has its own key, its own pacing and its own pause
# after "too many requests", and a provider that runs out of free requests hands over to the
# next model at once instead of waiting.
PROVIDERS = {
    #  name        base address                                              key setting           requests/min
    "nvidia":     ("https://integrate.api.nvidia.com/v1",                     "NVIDIA_API_KEY",     30),
    "ollama":     (os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434/v1"), None,                 0),
    "groq":       ("https://api.groq.com/openai/v1",                          "GROQ_API_KEY",       30),
    "cerebras":   ("https://api.cerebras.ai/v1",                              "CEREBRAS_API_KEY",   30),
    "openrouter": ("https://openrouter.ai/api/v1",                            "OPENROUTER_API_KEY", 20),
    "gemini":     ("https://generativelanguage.googleapis.com/v1beta/openai/", "GEMINI_API_KEY",    10),
    "github":     ("https://models.github.ai/inference",                      "GITHUB_TOKEN",       15),
    "mistral":    ("https://api.mistral.ai/v1",                               "MISTRAL_API_KEY",    30),
}


def split_model(model: str) -> tuple[str | None, str]:
    """'groq:llama-3.3-70b' -> ('groq', 'llama-3.3-70b'); 'qwen2.5:7b' or 'nvidia/x' -> (None, as is)."""
    head, sep, rest = (model or "").partition(":")
    if sep and rest and head.lower() in PROVIDERS:
        return head.lower(), rest
    return None, model


def _is_local(model: str) -> bool:
    """A model on your own computer: labelled 'ollama:', or unlabelled while AI_BASE_URL is local."""
    provider, _ = split_model(model)
    return provider == "ollama" or (provider is None and LOCAL_AI)


def provider_key_missing(model: str) -> str | None:
    """The setting to fill in when a provider's key is missing (None: nothing missing)."""
    provider, _ = split_model(model)
    if provider is None:
        return None
    key_setting = PROVIDERS[provider][1]
    return key_setting if key_setting and not os.getenv(key_setting, "").strip() else None


_provider_clients: dict = {}


def _client_for(model: str):
    """The connection for this model's provider (looked up at call time: tests replace `client`)."""
    provider, _ = split_model(model)
    if provider is None:
        return client
    if provider not in _provider_clients:
        base, key_setting, _ = PROVIDERS[provider]
        _provider_clients[provider] = OpenAI(
            base_url=base, api_key=(os.getenv(key_setting, "").strip() if key_setting else "") or "local",
            timeout=REQUEST_TIMEOUT, max_retries=0)
    return _provider_clients[provider]


class _ProviderGate:
    """Pacing and the pause after 'too many requests' for ONE labelled provider."""

    def __init__(self, provider: str):
        default_rpm = PROVIDERS[provider][2]
        self.rpm = max(0, int(os.getenv(f"{provider.upper()}_RPM", str(default_rpm))))
        self.lock = threading.Lock()
        self.next_start = 0.0
        self.cooldown_until = 0.0

    def wait(self) -> None:
        with self.lock:
            now = time.monotonic()
            start = max(now, self.next_start, self.cooldown_until)
            if self.rpm:
                self.next_start = start + 60.0 / self.rpm
        if start > now:
            _pause(start - now)

    def refused(self, error: Exception) -> None:
        pause = 30.0
        try:
            pause = max(pause, float(getattr(error, "response", None).headers.get("retry-after", 0)))
        except (TypeError, ValueError, AttributeError):
            pass
        with self.lock:
            self.cooldown_until = max(self.cooldown_until, time.monotonic() + min(pause, 600.0))


_gates: dict = {}
_gates_lock = threading.Lock()


def _gate_for(provider: str) -> "_ProviderGate":
    with _gates_lock:
        if provider not in _gates:
            _gates[provider] = _ProviderGate(provider)
        return _gates[provider]


def _call_provider(model: str, request):
    """One request to a labelled provider: its own pacing; a refusal pauses only that provider."""
    global request_count, refused_count
    provider, _ = split_model(model)
    if provider is None:
        return _call_api(request)
    gate = _gate_for(provider)
    gate.wait()
    with _slots:
        with _cooldown_lock:
            request_count += 1
        try:
            return request()
        except Exception as error:
            if _is_rate_limited(error):
                with _cooldown_lock:
                    refused_count += 1
                gate.refused(error)
            raise


def _pause(seconds: float) -> None:
    """Wait between retries (a separate function so tests can skip the waiting)."""
    time.sleep(seconds)


class AIServiceError(Exception):
    """Raised when the AI service keeps failing even after retrying."""


class ContextTooLongError(AIServiceError):
    """The prompt was bigger than the model accepts. The caller should split it and retry."""


class AccountProblemError(AIServiceError):
    """The API key is missing or refused: no other model would do better."""


class ModelUnavailableError(AIServiceError):
    """NVIDIA says this model doesn't exist (any more): 404 Not Found or 410 Gone."""


def _is_model_gone(error: Exception) -> bool:
    status = getattr(error, "status_code", None)
    if status == 410 or isinstance(error, openai.NotFoundError):
        return True
    # Some gateways answer 400 "model ... does not exist / is not available / deprecated".
    text = str(error).lower()
    return isinstance(error, openai.BadRequestError) and "model" in text and any(
        k in text for k in ("does not exist", "not found", "not available", "no longer", "deprecated",
                            "unknown model", "retired"))


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
    if LOCAL_AI and _is_model_gone(error):
        return (f"The local AI server at {AI_BASE_URL} doesn't have that model. Download it first, e.g. "
                f"`ollama pull {CHAT_MODEL}`, or set CHAT_MODEL / JUDGE_MODEL in backend/.env to one you have.")
    if _is_model_gone(error):
        # 410 Gone used to be retried 6 times (about a minute wasted per request).
        return ("NVIDIA doesn't recognise the model name; it may have been retired. "
                "Run python check_models.py (in backend/) to see the live models, then set "
                "CHAT_MODEL / JUDGE_MODEL / EMBED_MODEL in backend/.env.")
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
        except (ModelStrugglingError, ModelUnavailableError):
            raise                                # hand over to the next model at once
        except Exception as error:
            if _is_context_too_long(error):
                raise ContextTooLongError(f"{what} failed: the request was too long for the model.") from error
            problem = _permanent_problem(error)
            if problem:
                kind = (ModelUnavailableError if _is_model_gone(error)
                        else AccountProblemError if isinstance(error, (openai.AuthenticationError,
                                                                       openai.PermissionDeniedError))
                        else AIServiceError)
                raise kind(f"{what} failed: {problem}") from error
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
    hint = ""
    if isinstance(last_error, openai.APIConnectionError) and (LOCAL_AI or "ollama" in what):
        hint = (" (the local AI server dropped or refused the connection: check the Ollama app is running, "
                "`ollama ps`, and try MAX_PARALLEL_AI_CALLS=1 if the GPU runs out of memory)")
    raise AIServiceError(f"{what} failed after {attempts} tries: {last_error}{hint}") from last_error


# How much the model "thinks" before answering:
#   off  – answer directly. Fastest, and the most reliable at producing structured answers.
#   low  – a short think first, capped at CHAT_THINKING_BUDGET tokens.
#   on   – full thinking. Much slower; mainly useful for comparison.
#
# CHAT_THINKING          – the reader (default: off). The slow, high-volume step.
# CHAT_THINKING_JUDGING  – the judge (default: low). The deployed setup uses off, because
#                          Nemotron 3 Ultra crashed (500 errors) whenever asked to think; a
#                          model that crashes twice with thinking is switched to off
#                          automatically anyway (see _unsupported_modes).
def _mode(variable: str, default: str) -> str:
    value = os.getenv(variable, default).strip().lower()
    return value if value in ("off", "low", "on") else default


THINKING_MODE = _mode("CHAT_THINKING", "off")
if os.getenv("CHAT_DISABLE_THINKING", "").lower() == "true":   # older setting name
    THINKING_MODE = "off"
JUDGING_THINKING_MODE = _mode("CHAT_THINKING_JUDGING", "low")
DISABLE_THINKING = THINKING_MODE == "off"
THINKING_BUDGET = max(256, int(os.getenv("CHAT_THINKING_BUDGET", "2048")))
# "model|mode" pairs that failed: those calls use "off" instead (only for that model).
_unsupported_modes: set[str] = set()
_thinking_crashes: dict[str, int] = {}

# Randomness (0 = always the same answer). No randomness by default: the same chapter should
# give the same result every time, and the judge in particular must be repeatable.
TEMPERATURE = float(os.getenv("CHAT_TEMPERATURE", "0.0"))
JUDGE_TEMPERATURE = float(os.getenv("JUDGE_TEMPERATURE", "0.0"))


def _model_family(model: str) -> str:
    name = (model or "").lower()
    if "gpt-oss" in name:
        return "gpt-oss"
    if "deepseek" in name:
        return "deepseek"
    if any(k in name for k in ("llama", "mistral", "gemma", "phi-")):
        return "plain"            # these chat templates have no thinking switch
    return "enable_thinking"      # Nemotron, Qwen 3, Kimi and most NIM models


def _effective_mode(mode: str | None, model: str | None) -> str:
    mode = mode or THINKING_MODE
    return "off" if model and f"{model}|{mode}" in _unsupported_modes else mode


def _thinking_options(mode: str | None = None, model: str | None = None) -> dict:
    """
    The request fields that switch a model's thinking off / low / on. Each model family
    spells this differently; sending the Nemotron spelling to some models gets the request
    refused.
    """
    mode = _effective_mode(mode, model)
    provider = split_model(model or "")[0]
    if (LOCAL_AI and provider is None) or (provider is not None and provider != "nvidia"):
        return {}                 # local servers and other services: no NVIDIA thinking switches                 # a local server: pick a model that doesn't think (e.g. qwen2.5)
    family = _model_family(model or CHAT_MODEL)
    if family == "enable_thinking":
        kwargs = {"off": {"enable_thinking": False},
                  "low": {"enable_thinking": True, "low_effort": True},
                  "on": {"enable_thinking": True}}[mode]
        return {"extra_body": {"chat_template_kwargs": kwargs}}
    if family == "gpt-oss":         # can't switch reasoning off, only make it short
        return {"reasoning_effort": {"off": "low", "low": "low", "on": "medium"}[mode]}
    if family == "deepseek":
        return {"extra_body": {"chat_template_kwargs": {"thinking": mode != "off"}}}
    return {}


def _answer_space(max_tokens: int, thinking: str | None = None) -> int:
    """Room for the answer, plus room for thinking when the model thinks first."""
    extra = 0 if (thinking or THINKING_MODE) == "off" else THINKING_BUDGET
    return min(max_tokens + extra, MAX_TOKENS_CEILING)


# ---------------------------------------------------------------------------
# Model lists, retirement and failover
# ---------------------------------------------------------------------------
_models_lock = threading.Lock()
_retired: dict[str, str] = {}            # model -> what NVIDIA said; never asked again
_unhealthy_until: dict[str, float] = {}  # model -> time it may be tried again (set aside)
_switch_notes: list[str] = []            # human-readable "switched from X to Y" messages
_verified: set[str] = set()              # models that have answered (or failed normally) once
_first_contact: dict[str, threading.Lock] = defaultdict(threading.Lock)


class ModelStrugglingError(AIServiceError):
    """A model kept failing (server errors / garbled answers) while another model is available."""


def _normal_role(role: str | None) -> str:
    return "judge" if role == "judge" else "reader"


def _chain(role: str) -> list[str]:
    """The models a job may use, best first. Judging falls back to the readers."""
    if _normal_role(role) == "judge":
        readers = list(CHAT_MODELS) if JUDGE_FALLS_BACK_TO_READERS or not JUDGE_MODELS else []
        return list(dict.fromkeys(list(JUDGE_MODELS) + readers))
    return list(dict.fromkeys(CHAT_MODELS))


def _usable(role: str, exclude: set | None = None) -> list[str]:
    now = time.monotonic()
    exclude = exclude or set()
    with _models_lock:
        alive = [m for m in _chain(role) if m not in _retired and m not in exclude]
        healthy = [m for m in alive if _unhealthy_until.get(m, 0) <= now]
    # Everything set aside? Then the set-aside ones are better than nothing.
    return healthy or alive


def current_chat_model(role: str = "reader") -> str | None:
    """The model this job would use right now."""
    models = _usable(role)
    return models[0] if models else None


def models_for(role: str) -> list[str]:
    return _usable(role)


def _note(text: str) -> None:
    with _models_lock:
        _switch_notes.append(text)
    print(f"  [MODEL] {text}", flush=True)


def _mark_retired(model: str, error: Exception) -> None:
    with _models_lock:
        if model in _retired:
            return
        _retired[model] = str(error)[:300]
    if "so this model is skipped" in str(error):
        _note(str(error))
        return
    _note(f"'{model}' is not available any more; it won't be asked again. "
          f"Run python check_models.py (in backend/) and update CHAT_MODEL / JUDGE_MODEL.")


def _set_aside(model: str, error: Exception) -> None:
    with _models_lock:
        _unhealthy_until[model] = time.monotonic() + SET_ASIDE_SECONDS
    _note(f"'{model}' keeps failing ({str(error)[:120]}); using the next model for "
          f"{SET_ASIDE_SECONDS / 60:.0f} minutes.")


def struggling_models() -> list[str]:
    now = time.monotonic()
    with _models_lock:
        return sorted(m for m, until in _unhealthy_until.items() if until > now and m not in _retired)


def model_status() -> dict:
    """What /health and the evaluation report show about the models."""
    return {"reader": current_chat_model("reader"), "judge": current_chat_model("judge"),
            "configured": {"reader": CHAT_MODELS, "judge": JUDGE_MODELS, "embedding": EMBED_MODEL},
            "retired": dict(_retired), "struggling": struggling_models(), "notes": list(_switch_notes)}


def _all_gone_message(what: str, role: str) -> str:
    return (f"{what} failed: none of the configured models can be used; each was retired by NVIDIA "
            f"or kept failing ({', '.join(_chain(role))}). "
            f"Run python check_models.py (in backend/) to see which models your NVIDIA key can use, "
            f"then set CHAT_MODEL / JUDGE_MODEL in backend/.env.")


def _with_failover(role: str, what: str, attempt_with):
    """
    Run attempt_with(model, has_alternative) on the job's best model. A retired model
    (404/410) is never asked again; a struggling one is set aside; the next model takes over.
    """
    tried: set[str] = set()
    while True:
        candidates = _usable(role, exclude=tried)
        if not candidates:
            raise AIServiceError(_all_gone_message(what, role))
        model = candidates[0]
        has_alternative = len(candidates) > 1
        # The first request to a model goes alone: if the model is gone, the requests running
        # in parallel learn it from that one answer instead of each asking a dead model.
        lock = _first_contact[model] if model not in _verified else None
        try:
            if lock is not None:
                with lock:
                    if model in _retired:
                        tried.add(model)
                        continue
                    try:
                        return attempt_with(model, has_alternative)
                    finally:
                        if model not in _retired:
                            _verified.add(model)
            return attempt_with(model, has_alternative)
        except ModelUnavailableError as error:
            _mark_retired(model, error)
            tried.add(model)
        except ModelStrugglingError as error:
            _set_aside(model, error)
            tried.add(model)


MAX_TOKENS_CEILING = 16384


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


def _is_server_error(error: Exception) -> bool:
    return isinstance(error, openai.InternalServerError) or (getattr(error, "status_code", 0) or 0) >= 500


def _send(model: str, mode: str, make_request):
    """
    One request with a thinking setting. If the model refuses or crashes with thinking on,
    the setting is dropped for THIS model: at once for a refusal (400), after two crashes
    (500s) for a crash. Other models keep their thinking.
    """
    effective = _effective_mode(mode, model)
    if split_model(model)[0] is not None:
        call = lambda request: _call_provider(model, request)      # noqa: E731
    else:
        call = _call_api
    try:
        return call(lambda: make_request(effective))
    except Exception as error:
        if effective == "off" or _is_context_too_long(error) or _is_model_gone(error) or _is_rate_limited(error):
            raise
        key = f"{model}|{effective}"
        if isinstance(error, openai.BadRequestError):
            response = call(lambda: make_request("off"))
            _unsupported_modes.add(key)
            print(f"  [note] thinking '{effective}' was refused by {model}; it answers without thinking now",
                  flush=True)
            return response
        if _is_server_error(error):
            _thinking_crashes[key] = _thinking_crashes.get(key, 0) + 1
            if _thinking_crashes[key] >= 2:
                _unsupported_modes.add(key)
                print(f"  [note] {model} crashed twice while thinking; it answers without thinking now",
                      flush=True)
                return call(lambda: make_request("off"))
        raise


def _attempts(what: str, model: str, has_alternative: bool, ask_once):
    """Retries for one model: fewer when another model could take over."""
    missing = provider_key_missing(model)
    if missing:
        raise ModelUnavailableError(f"{model}: no {missing} in backend/.env, so this model is skipped")
    provider = split_model(model)[0]
    if provider is not None:
        def ask_once_checked(inner=ask_once):
            try:
                return inner()
            except (openai.AuthenticationError, openai.PermissionDeniedError) as error:
                key = PROVIDERS[provider][1] or "the key"
                raise ModelUnavailableError(f"{model}: {provider} rejected {key} in backend/.env, so this model "
                                            f"is skipped ({str(error)[:100]})") from error
        ask_once = ask_once_checked
    if split_model(model)[0] is not None and has_alternative:
        def ask_once_or_hand_over(inner=ask_once):
            try:
                return inner()
            except Exception as error:
                if _is_rate_limited(error):
                    raise ModelStrugglingError(f"{model} is out of free requests for now: {str(error)[:120]}") from error
                raise
        ask_once = ask_once_or_hand_over
    try:
        return with_retries(ask_once, what=f"{what} ({model})",
                            attempts=FAILOVER_AFTER if has_alternative else None)
    except (ModelUnavailableError, ContextTooLongError, AccountProblemError):
        raise
    except AIServiceError as error:
        if has_alternative and "Too Many Requests" not in str(error):
            raise ModelStrugglingError(str(error)) from error
        raise


def call_tool(prompt: str, tool: dict, max_tokens: int = 4096, thinking: str | None = None,
              role: str | None = None) -> dict:
    """
    Ask a chat model a question and force it to answer in the structured format described by
    `tool`. Returns the answer as a Python dict.

    role: "reader" (default: reading, timing; the fast models) or "judge" (linking, checking,
    double-check; the careful models).
    thinking: "off" / "low" / "on" (default: CHAT_THINKING for the reader, CHAT_THINKING_JUDGING
    for the judge).
    If the model answers in plain text instead, the JSON is taken from the text.
    If it ran out of space, the next try gets twice as much room.
    """
    role = _normal_role(role)
    tool_name = tool["function"]["name"]
    mode = thinking or (JUDGING_THINKING_MODE if role == "judge" else THINKING_MODE)
    temperature = JUDGE_TEMPERATURE if role == "judge" else TEMPERATURE

    def attempt_with(model: str, has_alternative: bool) -> dict:
        # The answer space only grows after an answer was actually CUT OFF (finish_reason
        # "length"). Refusals, outages and garbled answers retry with the same budget.
        state = {"budget": min(max_tokens, MAX_TOKENS_CEILING)}

        def ask_once():
            budget = state["budget"]

            def make_request(m):
                if _is_local(model):
                    # Local servers (Ollama) handle forced tool calls unreliably (empty answers):
                    # ask for plain JSON in the tool's shape instead.
                    schema = json.dumps(tool["function"].get("parameters", {}))
                    return _client_for(model).chat.completions.create(
                        model=split_model(model)[1], max_tokens=_answer_space(budget, m), temperature=temperature,
                        response_format={"type": "json_object"},
                        messages=[{"role": "user", "content":
                                   f"{prompt}\n\nAnswer with ONE JSON object only, no other text, matching this "
                                   f"JSON schema:\n{schema}"}])
                return _client_for(model).chat.completions.create(
                    model=split_model(model)[1], max_tokens=_answer_space(budget, m), temperature=temperature,
                    tools=[tool], tool_choice={"type": "function", "function": {"name": tool_name}},
                    messages=[{"role": "user", "content": prompt}], **_thinking_options(m, model))

            response = _send(model, mode, make_request)
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

        return _attempts(f"AI call '{tool_name}'", model, has_alternative, ask_once)

    return _with_failover(role, f"AI call '{tool_name}'", attempt_with)


def embed_texts(texts: list[str], input_type: str = "passage") -> list[list[float]]:
    """
    Turn many pieces of text into vectors (lists of numbers that capture meaning),
    sending them in batches instead of one request per text.

    input_type must be "passage" for text you STORE and "query" for text you
    SEARCH WITH. Mixing them up silently makes search worse.
    There is deliberately no automatic fallback here: vectors from a different model can't
    be compared with the stored ones. Change EMBED_MODEL and run reembed.py instead.
    """
    vectors: list[list[float]] = []
    for start in range(0, len(texts), EMBED_BATCH_SIZE):
        batch = texts[start:start + EMBED_BATCH_SIZE]
        response = with_retries(
            lambda: _call_api(lambda: _embed_client().embeddings.create(
                input=batch,
                model=EMBED_MODEL,
                **({"extra_body": {"input_type": input_type, "truncate": "END"}} if EMBED_IS_NVIDIA else {}),
            )),
            what="Embedding request",
        )
        # Put results back in the same order as the input, just in case.
        for item in sorted(response.data, key=lambda d: d.index):
            vectors.append(item.embedding)
    return vectors


def ask_text(prompt: str, max_tokens: int = 1024) -> str:
    """Ask a reader model for a plain written answer (used by the "Ask" box)."""
    def attempt_with(model: str, has_alternative: bool) -> str:
        def ask_once():
            def make_request(m):
                return _client_for(model).chat.completions.create(
                    model=split_model(model)[1], max_tokens=_answer_space(max_tokens, m), temperature=TEMPERATURE,
                    messages=[{"role": "user", "content": prompt}], **_thinking_options(m, model))
            response = _send(model, THINKING_MODE, make_request)
            text = response.choices[0].message.content or ""
            # Some models include their private reasoning in <think> tags; hide it.
            text = re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()
            if not text:
                raise ValueError("the model returned an empty answer")
            return text

        return _attempts("Answering the question", model, has_alternative, ask_once)

    return _with_failover("reader", "Answering the question", attempt_with)


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
