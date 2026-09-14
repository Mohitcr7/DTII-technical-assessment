"""Stance extraction: what position does a claim take on a shared axis?

Contradiction detection has to reason about *propositions*, not strings. Two
sentences conflict when they take incompatible positions on the same axis for
the same subject in the same period. So the system extracts a small typed
stance from each claim and compares stances, which is why it can say why a
conflict exists rather than that two documents "mention the same words".

Axes are declarative configuration. Adding an axis is a data change, and a
model can propose candidate axes for a human to accept - but the comparison
itself stays deterministic so the same corpus always yields the same findings.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .schemas import Claim


@dataclass(frozen=True)
class Position:
    name: str
    pattern: re.Pattern[str]
    gloss: str          # plain-language meaning, used in explanations


@dataclass(frozen=True)
class StanceAxis:
    """A proposition family whose positions are mutually exclusive."""

    name: str
    subject: str                     # what the axis is about, for explanations
    #: A claim must touch at least one of these to be on this axis at all.
    scope: set[str]
    positions: tuple[Position, ...]
    #: Why the positions cannot coexist - the semantic core of the explanation.
    incompatibility: str
    field_: str = field(default="", repr=False)


def _p(name: str, pattern: str, gloss: str) -> Position:
    return Position(name, re.compile(pattern, re.IGNORECASE), gloss)


# A claim that proposes, evaluates or questions something takes no position on
# the axis - it is a move in the deliberation, not an assertion about the world.
# Without this gate "evaluate a secondary provider" reads as "we have two".
_NON_ASSERTIVE = re.compile(
    r"\b(evaluat\w+|recommend\w*|consider\w*|assess\w*|whether|should we|action item"
    r"|proposed|propose|if true|may need|flagged for|no decision)\b"
    # Reported speech: a sentence *about* another document's position is not
    # itself a position. Without this, a changelog line arguing with DOC-02
    # would be scored as holding DOC-02's view.
    r"|\b(reverses|described in|referenced in|raised in|see)\s+(the\s+)?\w*\s*DOC-\d+"
    r"|\breverses the\b",
    re.IGNORECASE,
)


AXES: tuple[StanceAxis, ...] = (
    StanceAxis(
        name="custody_vendor_cardinality",
        subject="how many custody providers hold production signing keys",
        scope={"custody", "vendor", "coldvault", "keyforge", "provider"},
        positions=(
            # "single-vendor risk" argues *against* single-vendor, so the
            # bare word cannot be trusted; require it to attach to a provider
            # noun and not to a risk framing.
            _p("single",
               r"\b(exclusive|sole|single)\b(?![- ]vendor risk)[^.]{0,30}\b(provider|vendor|custodian|custody)\b(?!\s*risk)"
               r"|\bcustody provider\b[^.]{0,20}\b(exclusive|sole|only)\b"
               r"|\bwound down\b|\bconsolidat\w+\b",
               "exactly one provider is authorised for this function"),
            _p("multiple",
               r"\b(secondary|second|additional|backup)\s+(key-)?(custody\s+)?(provider|vendor|custodian)\b"
               r"|\balongside\b|\bboth providers\b"
               r"|\bmulti-(custody|vendor|region)\b|\btwo providers\b",
               "two or more providers serve this function concurrently"),
        ),
        incompatibility=(
            "Exclusivity is a cardinality claim about the same function at the same time: "
            "'exclusive provider' means at most one. A second provider running live in "
            "production for that same function makes the exclusivity claim false. The two "
            "statements are not different words for one arrangement - they describe "
            "arrangements that cannot both hold."
        ),
    ),
    StanceAxis(
        name="log_retention_period",
        subject="how long signing request logs are retained",
        scope={"retention", "logs", "policy"},
        positions=(
            _p("years", r"(\d+)\s*-?\s*year", "a specific retention duration in years"),
        ),
        incompatibility=(
            "A retention policy is single-valued for a given artifact class: the logs are "
            "kept for one duration, not two. Two different durations asserted as the policy "
            "cannot both be in force."
        ),
    ),
    StanceAxis(
        name="eu_region_decision",
        subject="whether a Frankfurt/EU custody region will be opened",
        scope={"frankfurt", "region", "eu", "latency"},
        positions=(
            _p("decided", r"\bwill open\b|\bapproved\b|\bdecision\s*:", "committed to opening a region"),
            _p("undecided", r"\bnot yet decided\b|\brecommendation, not a decision\b|\bmay need\b",
               "explicitly not yet decided"),
        ),
        incompatibility=(
            "A plan is either adopted or still open. Treating an unadopted recommendation "
            "as a decision manufactures institutional authority that nobody granted."
        ),
    ),
)

#: Numbers with units, for the generic numeric-divergence detector.
_QUANTITY = re.compile(
    r"(\d+(?:\.\d+)?)\s*-?\s*(year|years|month|months|hour|hours|minute|minutes|"
    r"ms|millisecond|milliseconds|%|percent|requests?/second)",
    re.IGNORECASE,
)

_UNIT_ALIASES = {
    "years": "year", "months": "month", "hours": "hour", "minutes": "minute",
    "milliseconds": "ms", "millisecond": "ms", "percent": "%", "requests/second": "rps",
    "request/second": "rps",
}


@dataclass
class Stance:
    axis: StanceAxis
    position: str
    gloss: str
    evidence_span: str


def stances_of(claim: Claim, *, assertive_only: bool = True) -> list[Stance]:
    """Every axis position this claim takes.

    With `assertive_only` (the default) non-assertive language yields nothing,
    so deliberation about an option is never mistaken for adoption of it. A
    *proposal* under evaluation is read with `assertive_only=False`: there we
    want the position it would establish, precisely so it can be checked
    against the decision already on record.
    """
    text = claim.text
    if assertive_only and _NON_ASSERTIVE.search(text):
        return []
    haystack = f"{text} {claim.doc_title}".lower()
    found: list[Stance] = []
    for axis in AXES:
        if not (axis.scope & set(claim.topics)) and not any(s in haystack for s in axis.scope):
            continue
        # When several positions match, the earliest match in the sentence is
        # the one the sentence is actually about; later ones are usually
        # subordinate clauses ("...to reduce single-vendor risk").
        hits = []
        for pos in axis.positions:
            m = pos.pattern.search(text)
            if m:
                label = pos.name
                if axis.name == "log_retention_period":
                    label = f"{m.group(1)}-year"
                hits.append((m.start(), Stance(axis, label, pos.gloss, m.group(0))))
        if hits:
            hits.sort(key=lambda h: h[0])
            found.append(hits[0][1])
    return found


def quantities(text: str) -> list[tuple[float, str]]:
    out: list[tuple[float, str]] = []
    for value, unit in _QUANTITY.findall(text):
        u = unit.lower()
        out.append((float(value), _UNIT_ALIASES.get(u, u)))
    return out
