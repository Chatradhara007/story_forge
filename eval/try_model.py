"""
Send ONE real reading request to a model and print the full answer or the full error.
Use it to see why a model is being set aside (the run log cuts error messages short).

    python eval/try_model.py groq:openai/gpt-oss-20b
    python eval/try_model.py nvidia:nvidia/nemotron-3.5-lightning-30b-a3b
"""
import json
import os
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND))
from dotenv import load_dotenv  # noqa: E402
load_dotenv(BACKEND / ".env")

import llm  # noqa: E402
import extract  # noqa: E402

model = sys.argv[1] if len(sys.argv) > 1 else llm.CHAT_MODELS[0]
text = ("Commander Yusra Adeyemi was forty-five and had been on Kestrel for three rotations. She was a tall woman "
        "with grey eyes and a burn scar on her left forearm. Haruki Mori was dead before the alarms stopped.")
prompt = extract.EXTRACTION_PROMPT.format(text=text, context="")
tool = extract.EXTRACTION_TOOL
print(f"Model: {model}   JSON mode: {llm._json_mode(model)}   answer room: {llm._cap_output(model, 8192)}")
try:
    if llm._json_mode(model):
        schema = json.dumps(tool["function"].get("parameters", {}))
        reply = llm._client_for(model).chat.completions.create(
            model=llm.split_model(model)[1], max_tokens=llm._cap_output(model, 8192), temperature=0,
            response_format={"type": "json_object"},
            messages=[{"role": "user", "content": f"{prompt}\n\nAnswer with ONE JSON object only, matching this JSON schema:\n{schema}"}])
    else:
        reply = llm._client_for(model).chat.completions.create(
            model=llm.split_model(model)[1], max_tokens=4096, temperature=0, tools=[tool],
            tool_choice={"type": "function", "function": {"name": tool["function"]["name"]}},
            messages=[{"role": "user", "content": prompt}])
    message = reply.choices[0].message
    print("FINISH:", reply.choices[0].finish_reason)
    print(message.tool_calls[0].function.arguments if message.tool_calls else message.content)
except Exception as error:  # noqa: BLE001
    print("FULL ERROR:\n", error)
