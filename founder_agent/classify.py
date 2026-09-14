"""Epistemic classification: FACT / INFERENCE / HYPOTHESIS / DECISION / UNKNOWN.

Rules first, model second.  A deterministic rule that fires with a quotable
trigger phrase is more trustworthy — and more auditable — than a model verdict,
so the model is only consulted when no rule fires.  Every label carries the
reason that produced it (`type_reason`), which is what makes "do not silently
convert one category into another" checkable after the fact.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .schemas import ClaimType

_RULES: list[tuple[ClaimType, float, str]] = []


@dataclass(frozen=True)
class Rule:
    claim_type: ClaimType
    pattern: re.Pattern[str]
    confidence: float
    label: str


def _r(ct: ClaimType, pat: str, conf: float, label: str) -> Rule:
    return Rule(ct, re.compile(pat, re.IGNORECASE), conf, label)


# Ordered by precedence. The first rule that matches wins, so explicit
# uncertainty markers must outrank everything: a sentence that says
# "hypothesis (untested)" is never a fact, however confidently it is phrased.
#
# Causal connectives ("due to", "because") are deliberately ranked *below*
# reported events. "Access was delayed due to infra work" is a fact with an
# explanation attached, not an inference - ranking the connective first would
# demote half the corpus into speculation.
RULES: list[Rule] = [
    # --- HYPOTHESIS: author flags the claim as unvalidated -----------------
    _r(ClaimType.HYPOTHESIS, r"\bhypothes[ie]s\b", 0.95, "self-labelled hypothesis"),
    _r(ClaimType.HYPOTHESIS, r"\buntested\b|\bnot (yet )?(been )?validated\b", 0.95, "explicitly unvalidated"),
    _r(ClaimType.HYPOTHESIS, r"\bnot confirmed\b|\bjust a concern\b", 0.9, "author disclaims confirmation"),
    _r(ClaimType.HYPOTHESIS, r"\bI (suspect|think|believe)\b", 0.85, "first-person speculation"),
    _r(ClaimType.HYPOTHESIS, r"\bif true\b|\bwe may (need|lose|have to)\b", 0.75, "speculative conditional"),

    # --- DECISION: an institutional choice that binds behaviour -----------
    _r(ClaimType.DECISION, r"^\s*decision\s*:", 0.98, "explicit 'Decision:' marker"),
    _r(ClaimType.DECISION, r"\b(the board|we) (reaffirmed|approved|resolved|ratified)\b", 0.92, "ratification verb"),
    _r(ClaimType.DECISION, r"\bwill (use|maintain|be retained|provide)\b.*\b(exclusive|sole|all|going forward)\b", 0.85, "binding commitment language"),
    _r(ClaimType.DECISION, r"\beffective immediately\b", 0.85, "effectivity clause"),
    _r(ClaimType.DECISION, r"\bshould be wound down\b", 0.8, "forward-binding directive"),

    # --- INFERENCE (strong): an explicit evidence-to-conclusion move -------
    _r(ClaimType.INFERENCE, r"\bthis supports\b|\bconsistent with\b", 0.9, "evidence-to-conclusion link"),
    _r(ClaimType.INFERENCE, r"\broot cause\s*:", 0.85, "causal attribution"),
    _r(ClaimType.INFERENCE, r"\brecommends?\b|\brecommendation\b", 0.85, "recommendation, not a decision"),
    _r(ClaimType.INFERENCE, r"\bbest practice\b|\bincreasingly favors\b", 0.8, "normative generalisation"),

    # --- FACT: observed, recorded or stated state -------------------------
    _r(ClaimType.FACT, r"^\s*\[SUPERSEDED\b", 0.9, "historical record of a superseded position"),
    _r(ClaimType.FACT, r"^\s*status\s*:", 0.85, "document status marker"),
    _r(ClaimType.FACT, r"\bwas delivered\b|\bexperienced\b|\b(was|were) delayed\b|\bwas notified\b"
                       r"|\bwe (pulled|reviewed|measured|collected|analysed|analyzed)\b"
                       r"|\b(passed|onboarded|delivered|committed)\b", 0.85, "reported past event"),
    _r(ClaimType.FACT, r"\bhas increased\b|\bare now live\b|\bis rate-limited\b|\buses\b"
                       r"|\bis current\b|\boccurs\b|\bauthenticate\b", 0.8, "reported current state"),
    _r(ClaimType.FACT, r"\ball .* (are|is) logged\b|\bnever leaves\b|\bis logged\b", 0.8, "stated system property"),
    _r(ClaimType.FACT, r"\d+(\.\d+)?\s*(%|ms|hours?|minutes?|years?|seconds?|requests?)", 0.75, "quantified measurement"),

    # --- INFERENCE (weak): a causal or hedged connective ------------------
    _r(ClaimType.INFERENCE, r"\bjustifies\b|\bdriven by\b|\bdue to\b|\bbecause\b", 0.65, "causal reasoning"),
    _r(ClaimType.INFERENCE, r"\bsuggests?\b|\blikely\b|\bappears to\b", 0.65, "hedged conclusion"),
]


#: Phrases that explicitly *deny* decision status. These veto a DECISION label
#: even when binding-sounding language is present in the same sentence — the
#: single most common way a prototype silently promotes a recommendation.
DECISION_VETO = re.compile(
    r"not (yet )?(a )?decision|no (formal )?decision (document )?(was )?(filed|made)"
    r"|still a recommendation|have not yet decided|no decision made yet",
    re.IGNORECASE,
)

#: Reported speech about a hypothesis ("this supports the hypothesis in X") is
#: an inference drawn from evidence, not a new hypothesis. Without this guard the
#: mere word "hypothesis" would drag a conclusion back down a category.
HYPOTHESIS_REPORTED = re.compile(
    r"(supports?|confirms?|refutes?|contradicts?|raised in|described in|per|see)\s+"
    r"(the\s+)?hypothes[ie]s",
    re.IGNORECASE,
)

COMMITMENT_MARKER = re.compile(
    r"\bcommitted to\b|\btold .* that\b|\bwould provide\b|\bwas a condition\b", re.IGNORECASE
)


class Classifier:
    """Rule-first classifier with an optional model fallback."""

    def __init__(self, provider=None) -> None:
        self._provider = provider

    def classify(self, text: str, *, doc_type: str = "") -> tuple[ClaimType, str, float]:
        vetoed = bool(DECISION_VETO.search(text))
        reported_hypothesis = bool(HYPOTHESIS_REPORTED.search(text))

        for rule in RULES:
            if not rule.pattern.search(text):
                continue
            if rule.claim_type is ClaimType.HYPOTHESIS and reported_hypothesis:
                continue
            if rule.claim_type is ClaimType.DECISION and vetoed:
                # Keep scanning: something here reads like a decision but the
                # text itself says it is not one.
                continue
            return rule.claim_type, rule.label, rule.confidence

        if vetoed:
            return (
                ClaimType.INFERENCE,
                "decision-shaped language explicitly disclaimed as not-a-decision",
                0.8,
            )

        # Commitments are promises about future conduct: factual about what was
        # said, but they are not governing decisions.
        if COMMITMENT_MARKER.search(text):
            return ClaimType.FACT, "recorded commitment (a promise that was made)", 0.8

        if doc_type in {"technical_note", "incident", "status_update"}:
            return ClaimType.FACT, f"declarative statement in a {doc_type}", 0.6

        if self._provider is not None:
            label = self._provider.classify_claim(text)
            if label is not None:
                return label, "model fallback", 0.5

        return ClaimType.UNKNOWN, "no epistemic marker matched", 0.3
