"""
Which AI models can StoryForge use with your NVIDIA key, today?

NVIDIA retires models from its free API regularly. Run this when StoryForge says a model
has been retired, or before deploying:

    cd backend
    python check_models.py

It lists the chat models your key can see, gives each candidate one small real test
(StoryForge needs structured "tool" answers, which not every model supports), checks the
embedding model, and prints the CHAT_MODEL line to put in backend/.env.
It uses a handful of requests. Nothing in your books is touched.
"""
import json
import sys
import time

import openai
import llm
from llm import client, CHAT_MODELS, JUDGE_MODELS, EMBED_MODEL, AI_CONFIGURED

# Model families worth testing when the configured ones are gone, best first.
timings: dict[str, float] = {}

PREFERRED = ("nemotron", "kimi", "deepseek", "qwen", "llama", "mistral", "gpt-oss", "gemma")
SKIP = ("embed", "rerank", "guard", "safety", "reward", "vision", "vl-", "parse", "ocr", "audio",
        "speech", "asr", "tts", "clip", "retriever", "detector", "diffusion", "image", "video",
        "translate", "coder-7b", "math")

TEST_TOOL = {"type": "function", "function": {
    "name": "record_fact",
    "description": "Record one fact.",
    "parameters": {"type": "object", "properties": {
        "entity": {"type": "string"}, "attribute": {"type": "string"}, "value": {"type": "string"}},
        "required": ["entity", "attribute", "value"]}}}


def test_chat(model: str, thinking: str = "off") -> tuple[bool, str]:
    started = time.perf_counter()
    try:
        r = client.chat.completions.create(
            model=model, max_tokens=llm._answer_space(300, thinking), temperature=0,
            **llm._thinking_options(thinking, model),
            messages=[{"role": "user", "content": "Record the fact in this sentence: Ines had grey eyes."}],
            tools=[TEST_TOOL], tool_choice={"type": "function", "function": {"name": "record_fact"}})
        msg = r.choices[0].message
        if msg.tool_calls:
            answer = json.loads(msg.tool_calls[0].function.arguments)
            ok = "grey" in json.dumps(answer).lower()
            seconds = time.perf_counter() - started
            if thinking == "off":
                timings[model] = seconds
            return ok, f"works, answered in {seconds:.1f}s" if ok else f"answered, but wrongly: {answer}"
        return False, "answered in plain text instead of a structured answer"
    except openai.APIStatusError as e:
        if e.status_code == 410:
            return False, "retired (410 Gone)"
        if e.status_code == 404:
            return False, "not found (404)"
        if e.status_code == 429:
            return False, "too many requests right now (429): try again in a minute"
        return False, f"error {e.status_code}: {str(e)[:120]}"
    except Exception as e:                        # network, garbled JSON...
        return False, f"failed: {str(e)[:120]}"


def main() -> int:
    if not AI_CONFIGURED:
        print("No NVIDIA_API_KEY is set. Put it in backend/.env first.")
        return 1
    print("Asking NVIDIA which models your key can see...")
    try:
        available = sorted(m.id for m in client.models.list().data)
    except Exception as e:
        print(f"Couldn't list models: {e}")
        available = []
    print(f"  {len(available)} models listed.\n")
    if "--list" in sys.argv:
        chat = [m for m in available if not any(x in m.lower() for x in SKIP)]
        print("Chat models your key can see (candidates for JUDGE_MODEL / CHAT_MODEL):")
        for m in chat:
            print(f"  {m}")
        print("\nTest any of them as the judge, on identical reading, with:")
        print('  python ../eval/run_eval.py --judges "model-a,model-b"')
        return 0

    def test_list(title: str, models: list[str], with_thinking: bool = False) -> list[str]:
        print(title)
        good = []
        for model in models:
            ok, note = test_chat(model)
            print(f"  {'OK  ' if ok else 'NO  '} {model}: {note}")
            if ok and with_thinking:
                # The judge thinks briefly before deciding (CHAT_THINKING_JUDGING=low, capped at
                # CHAT_THINKING_BUDGET tokens). Some models crash on that: StoryForge then judges
                # with them WITHOUT thinking, which is less accurate.
                t_ok, t_note = test_chat(model, "low")
                print(f"       with thinking (as the judge uses it): {t_note}")
                if not t_ok:
                    print("       -> this model would judge WITHOUT thinking; prefer one where this works.")
            if ok:
                good.append(model)
        return good

    readers = test_list("Testing the READER models (CHAT_MODEL: fast, reads every passage):", CHAT_MODELS)
    judges = test_list("\nTesting the JUDGE models (JUDGE_MODEL: accurate, makes the decisions):",
                       list(dict.fromkeys(JUDGE_MODELS)), with_thinking=True)
    working = list(dict.fromkeys(readers + judges))

    if (not readers or not judges) and available:
        print("\nLooking for other models that work (testing up to 8):")
        candidates = [m for m in available if m not in CHAT_MODELS and not any(s in m.lower() for s in SKIP)]
        candidates.sort(key=lambda m: next((i for i, f in enumerate(PREFERRED) if f in m.lower()), len(PREFERRED)))
        for model in candidates[:8]:
            ok, note = test_chat(model)
            print(f"  {'OK  ' if ok else 'NO  '} {model}: {note}")
            if ok:
                working.append(model)
            if len(working) >= 3:
                break

    print(f"\nTesting the embedding model {EMBED_MODEL}:")
    try:
        r = client.embeddings.create(input=["Ines had grey eyes."], model=EMBED_MODEL,
                                     extra_body={"input_type": "passage", "truncate": "END"})
        print(f"  OK   works, {len(r.data[0].embedding)} numbers per fact")
    except openai.APIStatusError as e:
        print(f"  NO   {'retired (410 Gone)' if e.status_code == 410 else f'error {e.status_code}'}")
        others = [m for m in available if "embed" in m.lower()]
        if others:
            print("  Embedding models your key can see: " + ", ".join(others))
            print("  Set EMBED_MODEL to one of them, then run `python reembed.py` once.")

    print()
    if working:
        # Whatever was found: the fastest working models read, the rest (and the configured
        # judges first) judge. A model answering a one-line test quickly isn't proof of
        # accuracy: compare with eval/run_eval.py before settling.
        if not readers:
            readers = sorted(working, key=lambda m: timings.get(m, 99))[:2]
        if not judges:
            judges = [m for m in sorted(working, key=lambda m: -timings.get(m, 0)) if m not in readers][:2] or readers
        print("Put these lines in backend/.env (or the host's environment settings), then restart:")
        print(f"  CHAT_MODEL={','.join(readers[:3])}")
        print(f"  JUDGE_MODEL={','.join(judges[:3])}")
        print("\nTo compare accuracy properly, run the evaluation with each setup:")
        print("  python ../eval/run_eval.py --runs 3")
        return 0
    print("No working chat model was found. Check https://build.nvidia.com/models for current models.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
