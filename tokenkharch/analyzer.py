from __future__ import annotations

import re
from collections import Counter
from dataclasses import asdict, dataclass

from .tokenizer import count_tokens

FILLERS = [
    r"\bplease\b", r"\bkindly\b", r"\bjust\b", r"\bbasically\b", r"\bactually\b",
    r"\breally\b", r"\bvery\b", r"\bfeel free to\b", r"\bi was wondering if\b",
    r"\bif you (?:could|can|would)\b", r"\bcould you\b",
]
BOILERPLATE = [
    r"you are an? (?:very )?(?:helpful|expert|experienced|professional|smart|world[- ]class)[^.\n]*[.\n]",
    r"as an ai(?: language model)?,?",
    r"make sure (?:to|that you)\b",
    r"it is (?:very )?important (?:to note )?that\b",
    r"do not (?:ever|under any circumstances)\b",
]
STOPWORDS = {"that", "this", "with", "from", "have", "your", "will", "what", "which", "about", "there", "their", "them", "they", "then", "than", "into", "should", "would", "could"}


@dataclass
class Issue:
    type: str
    severity: str        # high | medium | low
    description: str
    token_impact: int    # tokens attributable to this pattern
    examples: list[str]

    def to_dict(self) -> dict:
        return asdict(self)


def _matches(patterns: list[str], text: str) -> list[str]:
    hits: list[str] = []
    for p in patterns:
        hits += [m.group(0) for m in re.finditer(p, text, re.IGNORECASE)]
    return hits


def split_sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", text) if s.strip()]


def _norm(sentence: str) -> str:
    return re.sub(r"[^\w\s]", "", sentence.lower()).strip()


def analyze(prompt: str) -> list[Issue]:
    issues: list[Issue] = []
    total = count_tokens(prompt)

    fillers = _matches(FILLERS, prompt)
    if fillers:
        issues.append(Issue("filler_words", "low",
                            f"{len(fillers)} filler/hedging word(s). Models don't need politeness to follow instructions.",
                            sum(count_tokens(" " + f) for f in fillers), sorted(set(f.lower() for f in fillers))[:6]))

    boiler = _matches(BOILERPLATE, prompt)
    if boiler:
        issues.append(Issue("boilerplate", "medium",
                            f"{len(boiler)} boilerplate instruction(s). Replace role-priming with concrete requirements.",
                            sum(count_tokens(b) for b in boiler), [b.strip()[:60] for b in boiler][:4]))

    seen: dict[str, str] = {}
    dupes: list[str] = []
    for s in split_sentences(prompt):
        key = _norm(s)
        if len(key.split()) >= 3 and key in seen:
            dupes.append(s)
        seen.setdefault(key, s)
    if dupes:
        issues.append(Issue("duplicate_sentences", "high",
                            f"{len(dupes)} sentence(s) repeated verbatim. State each instruction once.",
                            sum(count_tokens(d) for d in dupes), dupes[:3]))

    words = [w for w in re.findall(r"\b[a-z]{4,}\b", prompt.lower()) if w not in STOPWORDS]
    repeats = [(w, c) for w, c in Counter(words).most_common(5) if c >= 4]
    if repeats:
        issues.append(Issue("repetition", "medium",
                            "Same terms repeated many times: " + ", ".join(f'"{w}" x{c}' for w, c in repeats[:3]) + ".",
                            sum(c - 1 for _, c in repeats[:3]), [w for w, _ in repeats[:3]]))

    if re.search(r"[ \t]{2,}|\n{3,}", prompt):
        ws = sum(len(m.group(0)) - 1 for m in re.finditer(r"[ \t]{2,}|\n{3,}", prompt))
        issues.append(Issue("whitespace", "low", "Extra spaces / blank lines cost tokens too.",
                            max(1, ws // 4), []))

    if total > 300 and "\n" not in prompt.strip():
        issues.append(Issue("unstructured", "high",
                            "Long prompt with no structure. Use sections (Task / Context / Constraints / Output).",
                            0, []))

    if total < 8:
        issues.append(Issue("underspecified", "low",
                            "Very short prompt - may be under-specified, causing longer back-and-forth (more tokens overall).",
                            0, []))

    order = {"high": 0, "medium": 1, "low": 2}
    return sorted(issues, key=lambda i: (order[i.severity], -i.token_impact))


def efficiency_score(prompt: str, issues: list[Issue] | None = None) -> int:
    """0-100: share of tokens that are *not* attributable to detected waste, minus structure penalties."""
    total = count_tokens(prompt)
    if total == 0:
        return 100
    issues = analyze(prompt) if issues is None else issues
    waste = sum(i.token_impact for i in issues)
    penalty = sum(5 for i in issues if i.type in ("unstructured", "underspecified"))
    return max(0, min(100, round(100 * (1 - waste / total)) - penalty))
