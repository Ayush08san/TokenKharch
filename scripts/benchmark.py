"""Reproducible savings benchmark: rules (safe + aggressive) vs. rules + local Ollama rewrite.

Run:  python scripts/benchmark.py            rules only
      python scripts/benchmark.py --local    also runs the Ollama stage (needs `ollama pull llama3.2:3b`)
"""
from __future__ import annotations

import argparse
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from tokenkharch import service  # noqa: E402
from tokenkharch.optimizer import optimize  # noqa: E402

PROMPTS = [
    "You are a very helpful assistant. Please could you just summarize this report in order to help me. Keep it short. Keep it short.",
    "You are an expert Python developer. I would like you to review the following function and make sure to point out any bugs. It is very important that you explain each issue clearly. Please be concise.",
    "Summarize the attached contract in five bullet points, focusing on payment terms, termination clauses and liability caps.",
    "I was wondering if you could help me write an email to my manager with regard to the delay in the project due to the fact that the vendor has not delivered. Keep it polite. Keep it polite.",
    "As an AI language model, you should really try to answer prior to asking follow-up questions. Basically, just give the answer first.",
    "Translate the following paragraph into French. Preserve formatting and do not add commentary.",
    "You are a world-class data analyst. Can you please analyse this CSV and tell me in order to improve sales which regions are underperforming? Actually, also include a chart description.",
    "Extract all dates and amounts from the invoice below and return them as JSON with keys date and amount.",
]


def pct(before: int, after: int) -> str:
    return f"{100 * (before - after) / before:.1f}%"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--local", action="store_true", help="also run the Ollama rewrite stage")
    ap.add_argument("--model", default=None, help="Ollama model (default: TOKENKHARCH_OLLAMA_MODEL or llama3.2:3b)")
    args = ap.parse_args()

    for mode in ("safe", "aggressive"):
        b = sum(optimize(p, mode)["tokens_before"] for p in PROMPTS)
        a = sum(optimize(p, mode)["tokens_after"] for p in PROMPTS)
        print(f"rules ({mode:<10}) {b} -> {a} tokens  ({pct(b, a)} saved)")

    if args.local:
        b = a = accepted = 0
        for p in PROMPTS:
            r = service.optimize_prompt_local(p, mode="safe", local_model=args.model)
            b, a = b + r["tokens_before"], a + r["tokens_after"]
            accepted += r["local_llm"]["accepted"]
            print(f"  {r['tokens_before']:>3} -> {r['tokens_after']:>3}  {r['local_llm']['reason']}")
        print(f"rules (safe) + {r['local_llm']['model']}: {b} -> {a} tokens  ({pct(b, a)} saved, "
              f"{accepted}/{len(PROMPTS)} rewrites accepted)")


if __name__ == "__main__":
    main()
