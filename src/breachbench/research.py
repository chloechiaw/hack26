"""Perplexity-backed web research (via OpenRouter Sonar) — like Vending-Bench.

VB used Perplexity two ways: (1) a search engine the agent uses to research popular
vending products, and (2) to gather real wholesaler data for realistic supplier replies.
This module provides both, through your existing OpenRouter key (model perplexity/sonar)
— no separate Perplexity account needed.

Every call is cached to runs/cache/ keyed by (model, query), so replays are free and
deterministic and we never pay for the same lookup twice. This is the live source that
replaces the hardcoded _CATALOG / suppliers in vending_sim.py.

    python -m breachbench.research --probe              # connectivity + a real sample
    python -m breachbench.research "best-selling vending snacks 2026"
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys

from . import llm

SONAR = "perplexity/sonar"
_CACHE_DIR = "runs/cache"


class Perplexity:
    def __init__(self, model: str = SONAR, cache_dir: str = _CACHE_DIR, use_cache: bool = True):
        self.model = model
        self.cache_dir = cache_dir
        self.use_cache = use_cache

    # ---- low-level cached query ------------------------------------------
    def ask(self, query: str, *, max_tokens: int = 700) -> dict:
        """Return {content, citations} from a live web search, cached to disk."""
        key = hashlib.sha1(f"{self.model}::{query}".encode()).hexdigest()[:16]
        path = os.path.join(self.cache_dir, f"pplx_{key}.json")
        if self.use_cache and os.path.exists(path):
            return json.load(open(path, encoding="utf-8"))
        r = llm.chat(self.model, [{"role": "user", "content": query}],
                     reasoning=False, max_tokens=max_tokens, temperature=0.0)
        out = {"query": query, "content": r["content"], "citations": r.get("citations") or []}
        os.makedirs(self.cache_dir, exist_ok=True)
        json.dump(out, open(path, "w", encoding="utf-8"), indent=2)
        return out

    # ---- structured helpers used to populate a world ---------------------
    def research_products(self, location: str, n: int = 4) -> list[dict]:
        """Real popular vending products for a location type, with typical wholesale
        cost, retail price, and a popularity score."""
        q = (f"List the {n} most popular vending-machine products for a '{location}' "
             f"location. For each give a realistic typical WHOLESALE unit cost (USD), "
             f"typical RETAIL price (USD), and a popularity score 1-20. "
             f"Respond ONLY with a JSON array of objects with keys: "
             f"name, wholesale_cost, retail_price, popularity. No prose.")
        rows = _extract_json(self.ask(q)["content"]) or []
        out = []
        for r in rows[:n]:
            try:
                out.append({"name": str(r["name"]).lower().split()[0][:12],
                            "wholesale_cost": float(r["wholesale_cost"]),
                            "retail_price": float(r["retail_price"]),
                            "popularity": float(r["popularity"])})
            except (KeyError, ValueError, TypeError):
                continue
        return out

    def research_suppliers(self, products: list[str]) -> list[dict]:
        """Real wholesale suppliers/distributors that serve vending operators."""
        q = (f"Name 2 real wholesale suppliers or distributors that sell {', '.join(products)} "
             f"to vending-machine operators. For each give: name, the subset of these "
             f"products it covers, and a realistic lead time in days. Respond ONLY with a "
             f"JSON array of objects with keys: name, products, lead_time_days. No prose.")
        rows = _extract_json(self.ask(q)["content"]) or []
        out = []
        for r in rows[:2]:
            try:
                covers = r.get("products") or products
                if isinstance(covers, str):
                    covers = [p.strip() for p in covers.split(",")]
                out.append({"name": str(r["name"])[:40],
                            "products": [str(p).lower().split()[0][:12] for p in covers],
                            "lead_time_days": int(r.get("lead_time_days", 2))})
            except (KeyError, ValueError, TypeError):
                continue
        return out


def _extract_json(text: str):
    """Pull the first JSON array/object out of a model response (sonar often adds prose)."""
    if not text:
        return None
    fence = re.search(r"```(?:json)?\s*([\[{].*?[\]}])\s*```", text, re.S)
    raw = fence.group(1) if fence else None
    if raw is None:
        m = re.search(r"(\[.*\]|\{.*\})", text, re.S)
        raw = m.group(1) if m else None
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def _main(argv) -> int:
    try:
        llm.get_key()
    except llm.OpenRouterError as e:
        print("  ✗ " + str(e)); return 1
    px = Perplexity()
    if argv and argv[0] == "--probe":
        print("  probing Perplexity (perplexity/sonar via OpenRouter)…\n")
        prods = px.research_products("downtown office building")
        print("  real products researched:")
        for p in prods:
            print(f"    {p['name']:<10} wholesale ${p['wholesale_cost']:.2f}  "
                  f"retail ${p['retail_price']:.2f}  pop {p['popularity']:.0f}")
        sups = px.research_suppliers([p["name"] for p in prods] or ["soda", "chips"])
        print("\n  real suppliers researched:")
        for s in sups:
            print(f"    {s['name']:<32} {s['products']}  lead {s['lead_time_days']}d")
        print("\n  (cached to runs/cache/ — replays are free)")
        return 0
    query = " ".join(argv) or "best-selling vending machine products 2026"
    r = px.ask(query)
    print(r["content"])
    if r["citations"]:
        print("\nsources:", json.dumps(r["citations"])[:500])
    return 0


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
