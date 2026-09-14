"""Lexical retrieval over claims (BM25) with topic and recency signals.

Deliberately dependency-free and deterministic: the same question returns the
same evidence every run, which is what makes the audit log worth keeping. An
embedding reranker can be layered on via `LLMProvider.embed`, but the system
must stay answerable with no network and no API key.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass

from .schemas import Claim, ClaimType, Evidence

_TOKEN = re.compile(r"[a-z0-9][a-z0-9\-.]*")

_STOP = {
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "to", "of", "and",
    "or", "in", "on", "for", "with", "that", "this", "it", "as", "at", "by", "we",
    "our", "us", "do", "does", "did", "has", "have", "had", "not", "no", "if",
    "what", "which", "who", "how", "why", "when", "can", "should", "would", "will",
}

# Query-side expansion: institutional vocabulary drifts between documents
# ("custody provider" / "vendor" / "HSM"), and a founder asks in their own words.
_SYNONYMS: dict[str, list[str]] = {
    "vendor": ["provider", "custody", "coldvault", "keyforge", "supplier"],
    "custody": ["custodian", "provider", "hsm", "coldvault", "keyforge"],
    "provider": ["vendor", "custody", "coldvault", "keyforge"],
    "retention": ["retain", "retained", "logs", "years"],
    "logs": ["logging", "retention", "retained"],
    "latency": ["slow", "delay", "ms", "round-trip", "eu", "region"],
    "region": ["regional", "frankfurt", "us-east-1", "eu"],
    "eu": ["europe", "european", "frankfurt", "regional"],
    "commitment": ["committed", "promised", "agreement", "condition"],
    "promise": ["commitment", "committed", "told", "agreement"],
    "customer": ["client", "partner", "northbridge", "halcyon", "pilot"],
    "attestation": ["report", "compliance", "northbridge", "signed"],
    "outage": ["downtime", "incident", "failure", "unavailable"],
    "cost": ["spend", "price", "expensive", "budget", "finance"],
    "auth": ["authentication", "oauth", "token", "credential"],
    "sandbox": ["halcyon", "partner", "api", "access"],
    "second": ["secondary", "backup", "redundancy", "multi"],
    "add": ["onboard", "onboarded", "introduce", "adopt"],
    "switch": ["migrate", "replace", "move", "change"],
    "key": ["signing", "hsm", "custody"],
    "algorithm": ["ecdsa", "p-256", "curve", "protocol", "signing"],
    "signing": ["sign", "ecdsa", "hsm", "protocol"],
    "encryption": ["ecdsa", "signing", "key", "hsm"],
}


def tokenize(text: str) -> list[str]:
    return [t for t in _TOKEN.findall(text.lower()) if t not in _STOP and len(t) > 1]


def expand(tokens: list[str]) -> list[str]:
    out = list(tokens)
    for t in tokens:
        out.extend(_SYNONYMS.get(t, []))
    return out


@dataclass
class _Doc:
    claim: Claim
    tokens: list[str]
    tf: Counter
    length: int


class ClaimIndex:
    """BM25 over claim text, with light structural boosts."""

    K1 = 1.4
    B = 0.72

    def __init__(self, claims: list[Claim]) -> None:
        self._docs: list[_Doc] = []
        for c in claims:
            toks = tokenize(f"{c.doc_title} {c.text}")
            self._docs.append(_Doc(c, toks, Counter(toks), len(toks)))
        self._avglen = (sum(d.length for d in self._docs) / len(self._docs)) if self._docs else 1.0
        self._df: Counter = Counter()
        for d in self._docs:
            self._df.update(set(d.tf))
        self._n = max(len(self._docs), 1)

    @property
    def claims(self) -> list[Claim]:
        return [d.claim for d in self._docs]

    def _idf(self, term: str) -> float:
        df = self._df.get(term, 0)
        return math.log(1 + (self._n - df + 0.5) / (df + 0.5))

    def search(
        self,
        query: str,
        *,
        top_k: int = 8,
        type_filter: set[ClaimType] | None = None,
        doc_filter: set[str] | None = None,
    ) -> list[Evidence]:
        q_tokens = tokenize(query)
        if not q_tokens:
            return []
        weighted: Counter = Counter()
        for t in q_tokens:
            weighted[t] += 1.0
        for t in expand(q_tokens):
            if t not in weighted:
                weighted[t] += 0.45  # expansion terms count less than the user's own words

        scored: list[tuple[float, _Doc]] = []
        for d in self._docs:
            if type_filter and d.claim.claim_type not in type_filter:
                continue
            if doc_filter and d.claim.doc_id not in doc_filter:
                continue
            score = 0.0
            for term, weight in weighted.items():
                f = d.tf.get(term, 0)
                if not f:
                    continue
                denom = f + self.K1 * (1 - self.B + self.B * d.length / self._avglen)
                score += weight * self._idf(term) * (f * (self.K1 + 1)) / denom
            if score <= 0:
                continue
            score *= self._structural_boost(d.claim, set(weighted))
            scored.append((score, d))

        scored.sort(key=lambda pair: (-pair[0], pair[1].claim.claim_id))
        return [
            Evidence(
                claim_id=d.claim.claim_id,
                doc_id=d.claim.doc_id,
                doc_title=d.claim.doc_title,
                source=d.claim.doc_source,
                date=d.claim.date,
                claim_type=d.claim.claim_type,
                text=d.claim.text,
                score=round(score, 4),
                flags=list(d.claim.injection_flags),
            )
            for score, d in scored[:top_k]
        ]

    @staticmethod
    def _structural_boost(claim: Claim, query_terms: set[str]) -> float:
        boost = 1.0
        boost += 0.08 * len(set(claim.topics) & query_terms)
        if claim.claim_type is ClaimType.DECISION:
            boost += 0.12          # governing records answer more questions
        if claim.injection_flags:
            boost -= 0.35          # never let suspicious text win on rank alone
        return max(boost, 0.1)
