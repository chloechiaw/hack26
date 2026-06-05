"""OpenRouter client — zero-dep (stdlib urllib), OpenAI-compatible chat + tool calling.

One place to talk to every model. Reads the key from OPENROUTER_API_KEY or a gitignored
.env at repo root. Captures `reasoning` (thinking) when the model exposes it.

Model slate = Opus 4.8 (the new frontier model to test) + the four most-cited
Vending-Bench models (Sonnet 3.5 best, o3-mini 2nd, GPT-4o, Gemini 1.5 Pro). Slugs are
best-effort; `python -m breachbench.live --ping` confirms which resolve on your account.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

# friendly name -> OpenRouter slug.
# NOTE (verified live, mid-2026): Claude 3.5 Sonnet and Gemini 1.5 Pro — both in the VB
# paper — are now RETIRED on OpenRouter (404). Slate below = what's reachable AND faithful:
# Opus 4.8 (the new model to test) + three real VB-paper models still hosted
# (Claude 3.5 Haiku, o3-mini, GPT-4o) + Gemini 2.5 Pro as the modern stand-in for VB's
# retired Gemini 1.5 Pro.
MODELS: dict[str, str] = {
    "opus-4.8":         "anthropic/claude-opus-4.8",   # NEW frontier model (not in VB paper)
    "sonnet-4.6":       "anthropic/claude-sonnet-4.6",  # frontier mid
    "haiku-3.5":        "anthropic/claude-3.5-haiku",   # VB-paper model (available) — cheap adversary
    "o3-mini":          "openai/o3-mini",               # VB-paper, 2nd best
    "gpt-4o":           "openai/gpt-4o",                # VB-paper (weak performer)
    "gpt-4o-mini":      "openai/gpt-4o-mini",           # fast/cheap
    "gemini-2.5-pro":   "google/gemini-2.5-pro",        # substitute for VB's retired Gemini 1.5 Pro
    "gemini-2.5-flash": "google/gemini-2.5-flash",      # fast/cheap + thinking traces
}


class OpenRouterError(RuntimeError):
    pass


def get_key() -> str:
    key = os.environ.get("OPENROUTER_API_KEY")
    if key:
        return key.strip()
    # fall back to a gitignored .env at repo root
    here = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    env_path = os.path.join(here, ".env")
    if os.path.exists(env_path):
        for line in open(env_path, encoding="utf-8"):
            line = line.strip()
            if line.startswith("OPENROUTER_API_KEY"):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise OpenRouterError(
        "no OPENROUTER_API_KEY found.\n"
        "  set it:   export OPENROUTER_API_KEY=sk-or-...\n"
        "  or write: echo 'OPENROUTER_API_KEY=sk-or-...' > .env   (gitignored)")


def resolve(model: str) -> str:
    """Accept a friendly name, a slug, or pass-through."""
    return MODELS.get(model, model)


def to_openai_tools(anthropic_tools: list[dict]) -> list[dict]:
    """Convert our {name, description, input_schema} tool defs to OpenAI function format."""
    return [{"type": "function", "function": {
        "name": t["name"], "description": t["description"], "parameters": t["input_schema"]}}
        for t in anthropic_tools]


def chat(model: str, messages: list[dict], *, tools: list[dict] | None = None,
         temperature: float = 0.0, max_tokens: int = 1024, reasoning: bool = True,
         timeout: float = 90.0) -> dict:
    """One chat completion. Returns {content, reasoning, tool_calls:[{id,name,args}],
    finish_reason, usage}. Raises OpenRouterError on transport/HTTP failure."""
    body: dict = {"model": resolve(model), "messages": messages,
                  "temperature": temperature, "max_tokens": max_tokens}
    if tools:
        body["tools"] = tools
    if reasoning:
        body["reasoning"] = {"effort": "low"}  # ask for thinking when the model supports it

    payload = json.dumps(body).encode()
    headers = {"Authorization": f"Bearer {get_key()}", "Content-Type": "application/json",
               "HTTP-Referer": "https://breachbench.local", "X-Title": "BreachBench"}
    # retry with backoff on rate-limit / transient errors (needed at 50-way concurrency)
    last = None
    for attempt in range(5):
        try:
            req = urllib.request.Request(OPENROUTER_URL, data=payload, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                data = json.loads(r.read().decode())
            break
        except urllib.error.HTTPError as e:
            detail = e.read().decode()[:400]
            last = OpenRouterError(f"HTTP {e.code} for {resolve(model)}: {detail}")
            if e.code in (429, 500, 502, 503, 529) and attempt < 4:
                time.sleep(min(2 ** attempt + 0.5 * attempt, 12))
                continue
            raise last from None
        except (urllib.error.URLError, TimeoutError) as e:
            last = OpenRouterError(f"network error for {resolve(model)}: {e}")
            if attempt < 4:
                time.sleep(min(2 ** attempt, 8))
                continue
            raise last from None
    else:
        raise last or OpenRouterError("exhausted retries")

    if "choices" not in data:
        raise OpenRouterError(f"unexpected response: {json.dumps(data)[:300]}")
    msg = data["choices"][0]["message"]
    tool_calls = []
    for tc in msg.get("tool_calls") or []:
        fn = tc.get("function", {})
        try:
            args = json.loads(fn.get("arguments") or "{}")
        except json.JSONDecodeError:
            args = {}
        tool_calls.append({"id": tc.get("id", ""), "name": fn.get("name", ""), "args": args})
    return {
        "content": msg.get("content") or "",
        "reasoning": msg.get("reasoning") or _reasoning_from_details(msg),
        "tool_calls": tool_calls,
        "citations": data.get("citations") or msg.get("annotations") or [],
        "finish_reason": data["choices"][0].get("finish_reason"),
        "usage": data.get("usage", {}),
        "raw_message": msg,
    }


def _reasoning_from_details(msg: dict) -> str | None:
    det = msg.get("reasoning_details")
    if isinstance(det, list):
        parts = [d.get("text", "") for d in det if isinstance(d, dict)]
        return "\n".join(p for p in parts if p) or None
    return None


def ping(model: str) -> dict:
    """Cheap connectivity check for one model. Returns {ok, slug, detail}."""
    slug = resolve(model)
    try:
        r = chat(model, [{"role": "user", "content": "reply with the single word: ok"}],
                 max_tokens=16, reasoning=False, timeout=40)
        return {"ok": True, "slug": slug, "detail": (r["content"] or "").strip()[:40]}
    except OpenRouterError as e:
        return {"ok": False, "slug": slug, "detail": str(e).splitlines()[0][:120]}
