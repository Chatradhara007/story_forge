"""
Everything that talks to the NVIDIA AI service lives here, in one place.

Before, the model names and the connection were copy-pasted into three files,
so changing a model meant remembering to edit all three. Now you change it once
here (or in your .env file).
"""
import os
import json
import re
import time
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

CHAT_MODEL = os.getenv("CHAT_MODEL", "nvidia/nemotron-3-super-120b-a12b")
EMBED_MODEL = os.getenv("EMBED_MODEL", "nvidia/nemotron-3-embed-1b")
EMBED_BATCH_SIZE = 32  # how many facts to turn into vectors in one request

client = OpenAI(
    base_url="https://integrate.api.nvidia.com/v1",
    api_key=os.environ["NVIDIA_API_KEY"],
)


class AIServiceError(Exception):
    """Raised when the AI service keeps failing even after retrying."""


def with_retries(action, what: str, attempts: int = 3, wait_seconds: float = 2):
    """
    Try `action` up to `attempts` times, waiting a bit longer after each failure.
    The AI service sometimes fails for a moment (busy, network hiccup, a garbled
    answer), and simply trying again usually works.
    """
    last_error = None
    for attempt in range(1, attempts + 1):
        try:
            return action()
        except Exception as error:
            last_error = error
            if attempt < attempts:
                time.sleep(wait_seconds * attempt)
    raise AIServiceError(f"{what} failed after {attempts} tries: {last_error}") from last_error


def call_tool(prompt: str, tool: dict, max_tokens: int = 4096) -> dict:
    """
    Ask the chat model a question and force it to answer in the structured
    format described by `tool`. Returns the answer as a Python dict.
    """
    tool_name = tool["function"]["name"]

    def ask_once():
        response = client.chat.completions.create(
            model=CHAT_MODEL,
            max_tokens=max_tokens,
            tools=[tool],
            tool_choice={"type": "function", "function": {"name": tool_name}},
            messages=[{"role": "user", "content": prompt}],
        )
        message = response.choices[0].message
        if not message.tool_calls:
            raise ValueError("the model did not return a structured answer")
        # If the answer was cut off or garbled, this raises and we retry.
        return json.loads(message.tool_calls[0].function.arguments)

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
            lambda: client.embeddings.create(
                input=batch,
                model=EMBED_MODEL,
                extra_body={"input_type": input_type, "truncate": "END"},
            ),
            what="Embedding request",
        )
        # Put results back in the same order as the input, just in case.
        for item in sorted(response.data, key=lambda d: d.index):
            vectors.append(item.embedding)
    return vectors


def ask_text(prompt: str, max_tokens: int = 1024) -> str:
    """Ask the chat model for a plain written answer (used by the "Ask" box)."""
    def ask_once():
        response = client.chat.completions.create(
            model=CHAT_MODEL,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.choices[0].message.content or ""
        # Some models include their private reasoning in <think> tags; hide it.
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()
        if not text:
            raise ValueError("the model returned an empty answer")
        return text

    return with_retries(ask_once, what="Answering the question")
