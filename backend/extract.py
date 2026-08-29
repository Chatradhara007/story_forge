import os
import json
from openai import OpenAI
from models import Fact, ExtractionResult

client = OpenAI(
    base_url="https://integrate.api.nvidia.com/v1",
    api_key=os.environ["NVIDIA_API_KEY"],
)

MODEL = "meta/llama-3.1-70b-instruct"  

EXTRACTION_TOOL = {
    "type": "function",
    "function": {
        "name": "record_facts",
        "description": "Record structured facts extracted from a story chapter.",
        "parameters": {
            "type": "object",
            "properties": {
                "facts": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "entity": {"type": "string"},
                            "entity_type": {
                                "type": "string",
                                "enum": ["character", "location", "item", "event", "other"]
                            },
                            "attribute": {"type": "string"},
                            "value": {"type": "string"},
                            "source_quote": {"type": "string"},
                            "confidence": {"type": "number"}
                        },
                        "required": ["entity", "entity_type", "attribute", "value", "source_quote", "confidence"]
                    }
                }
            },
            "required": ["facts"]
        }
    }
}

EXTRACTION_PROMPT = """You are extracting structured facts from a chapter of fiction for a
continuity-tracking system. Read the text and extract every concrete, checkable fact about
characters, locations, items, and events: physical descriptions, relationships, status
(alive/dead/injured), locations, dates/time references, and stated events.

Only extract facts that are explicitly stated or very strongly implied — do not infer
beyond what the text supports. Include a short exact quote for each fact so it can be
cited later.

Chapter text:
{text}
"""


def extract_facts(chapter_id: str, text: str) -> ExtractionResult:
    response = client.chat.completions.create(
        model=MODEL,
        max_tokens=4096,
        tools=[EXTRACTION_TOOL],
        tool_choice={"type": "function", "function": {"name": "record_facts"}},
        messages=[
            {"role": "user", "content": EXTRACTION_PROMPT.format(text=text)}
        ]
    )

    tool_call = response.choices[0].message.tool_calls[0]
    raw_facts = json.loads(tool_call.function.arguments)["facts"]
    facts = [Fact(**f) for f in raw_facts]

    return ExtractionResult(chapter_id=chapter_id, facts=facts)


# --- Fallback path ---
# If tool_choice forcing fails or returns empty tool_calls on your chosen NIM model,
# try dropping `tool_choice` entirely first (the model usually still calls the only
# tool offered). If that's still unreliable, use this instead: prompt the model to
# output raw JSON and parse `response.choices[0].message.content` directly.
#
# def extract_facts_fallback(chapter_id: str, text: str) -> ExtractionResult:
#     json_prompt = EXTRACTION_PROMPT.format(text=text) + \
#         "\n\nRespond with ONLY a JSON object of the form " \
#         '{"facts": [{"entity": ..., "entity_type": ..., "attribute": ..., ' \
#         '"value": ..., "source_quote": ..., "confidence": ...}]}. No other text.'
#     response = client.chat.completions.create(
#         model=MODEL,
#         max_tokens=4096,
#         messages=[{"role": "user", "content": json_prompt}]
#     )
#     raw = response.choices[0].message.content
#     raw_facts = json.loads(raw)["facts"]
#     facts = [Fact(**f) for f in raw_facts]
#     return ExtractionResult(chapter_id=chapter_id, facts=facts)
