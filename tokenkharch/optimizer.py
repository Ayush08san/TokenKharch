"""Rule-based prompt rewriter. Each rule's savings is measured by re-tokenizing, so reported numbers are real."""
from __future__ import annotations

import difflib
import re
from dataclasses import dataclass
from typing import Callable

from .analyzer import _norm, split_sentences
from .tokenizer import count_tokens

# (pattern, replacement) - concise equivalents of wordy phrases. Meaning-preserving.
VERBOSE_PHRASES: list[tuple[str, str]] = [
    (r"\bin order to\b", "to"),
    (r"\bdue to the fact that\b", "because"),
    (r"\bat this point in time\b", "now"),
    (r"\bfor the purpose of\b", "to"),
    (r"\bin the event that\b", "if"),
    (r"\ba (?:large|great) number of\b", "many"),
    (r"\bhas the ability to\b", "can"),
    (r"\bis able to\b", "can"),
    (r"\bin spite of the fact that\b", "although"),
    (r"\bwith regard to\b", "about"),
    (r"\bprior to\b", "before"),
    (r"\bin addition to\b", "besides"),
    (r"\bit is (?:very )?important (?:to note )?that\s+", ""),
    (r"\bmake sure (?:to|that you)\s+", ""),
    (r"\bi would like you to\s+", ""),
    (r"\bi want you to\s+", ""),
    (r"\bcan you (?:please )?", ""),
]

# Filler / hedging - removed in 'aggressive' mode only.
FILLER_PHRASES = [
    r"\bi was wondering if you could\s+", r"\bi was wondering if\s+", r"\bif you (?:could|can|would)\s+",
    r"\bcould you\s+", r"\bfeel free to\s+", r"\bplease\s+", r"\bkindly\s+",
    r"\bjust\s+", r"\bbasically\s+", r"\bactually\s+", r"\breally\s+",
]

ROLE_BOILERPLATE = r"\b(?:you are an? (?:very )?(?:helpful|expert|experienced|professional|smart|world[- ]class)[^.\n]*[.\n]\s*|as an ai(?: language model)?,?\s*)"


@dataclass
class Rule:
    name: str
    fn: Callable[[str], str]
    modes: tuple[str, ...]


def _sub_all(pairs: list[tuple[str, str]]) -> Callable[[str], str]:
    def run(text: str) -> str:
        for p, r in pairs:
            text = re.sub(p, r, text, flags=re.IGNORECASE)
        return text
    return run


def _dedupe_sentences(text: str) -> str:
    seen, out = set(), []
    for s in split_sentences(text):
        key = _norm(s)
        if len(key.split()) >= 3 and key in seen:
            continue
        seen.add(key)
        out.append(s)
    # keep paragraph structure roughly: join with newline if original had newlines
    sep = "\n" if "\n" in text else " "
    return sep.join(out)


def _collapse_whitespace(text: str) -> str:
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r" +([,.;:!?])", r"\1", text)
    return text.strip()


def _fix_capitals(text: str) -> str:
    text = re.sub(r"(^|[.!?]\s+|\n)([a-z])", lambda m: m.group(1) + m.group(2).upper(), text)
    return text


RULES: list[Rule] = [
    Rule("Removed duplicate sentences", _dedupe_sentences, ("safe", "aggressive")),
    Rule("Shortened wordy phrases", _sub_all(VERBOSE_PHRASES), ("safe", "aggressive")),
    Rule("Removed role-play boilerplate", lambda t: re.sub(ROLE_BOILERPLATE, "", t, flags=re.IGNORECASE), ("aggressive",)),
    Rule("Removed filler & hedging words", _sub_all([(p, "") for p in FILLER_PHRASES]), ("aggressive",)),
    Rule("Collapsed extra whitespace", _collapse_whitespace, ("safe", "aggressive")),
]


def word_diff(before: str, after: str) -> list[dict]:
    """Word-level diff as [{op: equal|delete|insert, text}] for the UI."""
    a, b = re.findall(r"\S+|\s+", before), re.findall(r"\S+|\s+", after)
    out: list[dict] = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if op == "equal":
            out.append({"op": "equal", "text": "".join(a[i1:i2])})
        else:
            if i2 > i1:
                out.append({"op": "delete", "text": "".join(a[i1:i2])})
            if j2 > j1:
                out.append({"op": "insert", "text": "".join(b[j1:j2])})
    return out


def optimize(prompt: str, mode: str = "aggressive") -> dict:
    if mode not in ("safe", "aggressive"):
        raise ValueError("mode must be 'safe' or 'aggressive'")
    before_tokens = count_tokens(prompt)
    text, applied = prompt, []
    for rule in RULES:
        if mode not in rule.modes:
            continue
        new = rule.fn(text)
        if new != text:
            saved = count_tokens(text) - count_tokens(new)
            applied.append({"rule": rule.name, "tokens_saved": saved})
            text = new
    text = _fix_capitals(_collapse_whitespace(text))
    after_tokens = count_tokens(text)
    saved = before_tokens - after_tokens
    return {
        "mode": mode,
        "original": prompt,
        "optimized": text,
        "tokens_before": before_tokens,
        "tokens_after": after_tokens,
        "tokens_saved": saved,
        "reduction_pct": round(100 * saved / before_tokens, 1) if before_tokens else 0.0,
        "applied": applied,
        "diff": word_diff(prompt, text),
    }
