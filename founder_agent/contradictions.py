"""Contradiction and supersession detection (assessment 2.3).

Five detectors, each of which produces an explanation of *why* two statements
are incompatible - the axis they share, and the semantic reason both cannot
hold - plus a resolution saying which record governs and on what authority.

Detection is structural and repeatable. A model, where configured, is used
afterwards to sharpen wording; it is never the thing that decides whether a
contradiction exists, because a flaky detector in institutional memory is worse
than none.
"""

from __future__ import annotations

import hashlib
import re
from datetime import date

from .schemas import (
    AUTHORITY_RANK,
    Claim,
    ClaimType,
    Contradiction,
    Evidence,
)
from .schemas import ContradictionCluster
from .stance import quantities, stances_of

_SEVERITY_RANK = {"high": 0, "medium": 1, "low": 2}

#: Lower number = more specific finding, wins the dedup for a given claim pair.
_SPECIFICITY = {
    "explicit_supersession": 0,
    "commitment_breach": 1,
    "unratified_change": 2,
    "numeric_divergence": 3,
    "mutual_exclusivity": 4,
    "external_divergence": 5,
}

_CLUSTER_TITLES = {
    "custody_vendor_cardinality": "How many custody providers govern production signing keys",
    "log_retention_period": "How long signing logs are retained",
    "unratified_change": "Production changed without a decision record",
    "commitment_breach": "External commitment not met on its original terms",
    "explicit_supersession": "Policy superseded in the record",
    "external_divergence": "Internal decision diverges from stated industry practice",
}

_DELAY = re.compile(r"\b(delayed|slipped|slip|postponed|pushed|missed|late|behind schedule)\b", re.I)
_DEADLINE = re.compile(
    r"\bby (end of |mid-|the end of )?(january|february|march|april|may|june|july|august|"
    r"september|october|november|december)\b|\bstarting Q[1-4]\b|\bby Q[1-4]\b", re.I)
_NO_FORMAL_DECISION = re.compile(
    r"no formal decision document was filed|no decision (document )?was (filed|made)"
    r"|rolled out as part of", re.I)


def _ev(claim: Claim, *, caveat: str | None = None) -> Evidence:
    return Evidence(
        claim_id=claim.claim_id,
        doc_id=claim.doc_id,
        doc_title=claim.doc_title,
        source=claim.doc_source,
        date=claim.date,
        claim_type=claim.claim_type,
        text=claim.text,
        score=0.0,
        caveat=caveat,
    )


def _cid(kind: str, a: str, b: str) -> str:
    digest = hashlib.sha256(f"{kind}|{a}|{b}".encode()).hexdigest()[:8]
    return f"ctr_{digest}"


def _order(a: Claim, b: Claim) -> tuple[Claim, Claim]:
    """Earlier claim first, so explanations read chronologically."""
    da, db = a.date or date.min, b.date or date.min
    return (a, b) if (da, a.claim_id) <= (db, b.claim_id) else (b, a)


def _authority_note(earlier: Claim, later: Claim) -> str:
    ra, rb = AUTHORITY_RANK.get(earlier.authority, 0), AUTHORITY_RANK.get(later.authority, 0)
    if rb > ra:
        return (f"{later.doc_id} carries higher authority ({later.authority.value} over "
                f"{earlier.authority.value}) as well as being later.")
    if rb < ra:
        return (f"{later.doc_id} is later but carries lower authority "
                f"({later.authority.value} vs {earlier.authority.value}), so recency alone "
                f"does not settle it.")
    return f"Both records carry {later.authority.value} authority, so recency decides."


class ContradictionDetector:
    def __init__(
        self,
        claims: list[Claim],
        documents: dict[str, object] | None = None,
        ledger: object | None = None,
    ) -> None:
        self.claims = claims
        self.documents = documents or {}
        #: Optional decision ledger, used to state what governs today. A
        #: contradiction report that stops at "these disagree" leaves the reader
        #: exactly where they started.
        self.ledger = ledger

    def detect_all(self) -> list[Contradiction]:
        found: list[Contradiction] = []
        found += self._explicit_supersession()
        found += self._stance_conflicts()
        found += self._numeric_divergence()
        found += self._unratified_change()
        found += self._commitment_breach()
        found += self._external_divergence()

        # One claim pair yields at most one finding. When several detectors fire
        # on the same pair the most specific wins, so a conflict the corpus has
        # already resolved is not also reported as an open one.
        best: dict[str, Contradiction] = {}
        for c in found:
            key = "|".join(sorted((c.claim_a.claim_id, c.claim_b.claim_id)))
            incumbent = best.get(key)
            if incumbent is None or _SPECIFICITY[c.kind] < _SPECIFICITY[incumbent.kind]:
                best[key] = c
        unique = list(best.values())
        unique.sort(key=lambda c: (_SEVERITY_RANK[c.severity], -c.confidence, c.contradiction_id))
        return unique

    def cluster(self, contradictions: list[Contradiction] | None = None) -> list[ContradictionCluster]:
        """Group findings into the underlying institutional issues.

        The custody question produces several conflicting pairs, but a founder
        has one problem, not five. Clustering keeps every pair as evidence while
        presenting the issue once.
        """
        items = contradictions if contradictions is not None else self.detect_all()
        buckets: dict[str, list[Contradiction]] = {}
        for c in items:
            axis = c.detector.split(":", 1)[1].strip() if c.detector.startswith("stance axis") else c.kind
            buckets.setdefault(axis, []).append(c)

        clusters: list[ContradictionCluster] = []
        for axis, group in buckets.items():
            group.sort(key=lambda c: (_SEVERITY_RANK[c.severity], -c.confidence))
            primary = group[0]
            docs = sorted({d for c in group for d in (c.claim_a.doc_id, c.claim_b.doc_id)})
            clusters.append(ContradictionCluster(
                cluster_id=f"cl_{hashlib.sha256(axis.encode()).hexdigest()[:8]}",
                axis=axis,
                title=_CLUSTER_TITLES.get(axis, axis.replace("_", " ")),
                severity=primary.severity,
                documents=docs,
                primary=primary,
                supporting=group[1:],
                current_position=self._current_position(docs),
            ))
        clusters.sort(key=lambda c: (_SEVERITY_RANK[c.severity], c.cluster_id))
        return clusters

    # -- detector 1: the corpus says so itself -----------------------------
    def _explicit_supersession(self) -> list[Contradiction]:
        out: list[Contradiction] = []
        by_doc: dict[str, list[Claim]] = {}
        for c in self.claims:
            by_doc.setdefault(c.doc_id, []).append(c)

        for doc_id, doc in self.documents.items():
            successor = getattr(doc, "superseded_by", None)
            if not successor or successor not in by_doc:
                continue
            old = by_doc.get(doc_id, [])
            new = by_doc.get(successor, [])
            if not old or not new:
                continue
            a, b = old[0], new[0]
            out.append(Contradiction(
                contradiction_id=_cid("explicit_supersession", a.claim_id, b.claim_id),
                kind="explicit_supersession",
                severity="low",
                confidence=0.99,
                claim_a=_ev(a, caveat=f"superseded by {successor}"),
                claim_b=_ev(b),
                why=(f"{doc_id} and {successor} set the same policy to different values. "
                     f"{doc_id} carries an explicit supersession marker naming {successor}, so "
                     f"the corpus itself records that the earlier position is no longer in force. "
                     f"The conflict is real but already resolved in the record."),
                resolution=(f"{successor} governs. {doc_id} is retained as history and must not be "
                            f"cited as current policy."),
                detector="frontmatter supersession marker",
            ))
        return out

    # -- detector 2: incompatible positions on a shared axis ---------------
    def _stance_conflicts(self) -> list[Contradiction]:
        out: list[Contradiction] = []
        # A hypothesis cannot contradict a decision: they are different kinds of
        # statement about the world. Letting them collide here would be exactly
        # the silent category conversion the classifier exists to prevent.
        eligible = [
            c for c in self.claims
            if c.claim_type in {ClaimType.FACT, ClaimType.DECISION, ClaimType.INFERENCE}
            and c.authority.value != "external"
        ]
        indexed = [(c, s) for c in eligible for s in stances_of(c)]
        for i, (claim_a, stance_a) in enumerate(indexed):
            for claim_b, stance_b in indexed[i + 1:]:
                if claim_a.doc_id == claim_b.doc_id:
                    continue
                if stance_a.axis.name != stance_b.axis.name:
                    continue
                if stance_a.position == stance_b.position:
                    continue
                # At least one side must be an assertion of record; two
                # downstream inferences disagreeing is an analysis gap, not an
                # institutional contradiction.
                if ClaimType.DECISION not in {claim_a.claim_type, claim_b.claim_type} and \
                   ClaimType.FACT not in {claim_a.claim_type, claim_b.claim_type}:
                    continue
                earlier, later = _order(claim_a, claim_b)
                e_stance = stance_a if earlier is claim_a else stance_b
                l_stance = stance_b if earlier is claim_a else stance_a

                governs = self._which_governs(earlier, later)
                severity = "high" if ClaimType.DECISION in {earlier.claim_type, later.claim_type} else "medium"
                out.append(Contradiction(
                    contradiction_id=_cid("mutual_exclusivity", earlier.claim_id, later.claim_id),
                    kind="mutual_exclusivity",
                    severity=severity,
                    confidence=0.9,
                    claim_a=_ev(earlier),
                    claim_b=_ev(later),
                    why=(
                        f"Both statements take a position on the same axis: {stance_a.axis.subject}. "
                        f"{earlier.doc_id} ({earlier.date}) asserts '{e_stance.position}' - "
                        f"{e_stance.gloss}. {later.doc_id} ({later.date}) asserts "
                        f"'{l_stance.position}' - {l_stance.gloss}. {stance_a.axis.incompatibility}"
                    ),
                    resolution=governs,
                    detector=f"stance axis: {stance_a.axis.name}",
                ))
        return out

    # -- detector 3: same measured quantity, different value ---------------
    def _numeric_divergence(self) -> list[Contradiction]:
        out: list[Contradiction] = []
        candidates = [(c, quantities(c.text)) for c in self.claims]
        candidates = [(c, q) for c, q in candidates if q]
        for i, (claim_a, qa) in enumerate(candidates):
            for claim_b, qb in candidates[i + 1:]:
                if claim_a.doc_id == claim_b.doc_id:
                    continue
                shared_topics = set(claim_a.topics) & set(claim_b.topics)
                if len(shared_topics) < 2:
                    continue
                for va, ua in qa:
                    for vb, ub in qb:
                        if ua != ub or va == vb:
                            continue
                        if ua not in {"year", "month"}:
                            continue   # durations of policy, not incidental measurements
                        earlier, later = _order(claim_a, claim_b)
                        out.append(Contradiction(
                            contradiction_id=_cid("numeric", earlier.claim_id, later.claim_id),
                            kind="numeric_divergence",
                            severity="medium",
                            confidence=0.85,
                            claim_a=_ev(earlier),
                            claim_b=_ev(later),
                            why=(
                                f"Both claims assign a single-valued policy parameter over "
                                f"{sorted(shared_topics)}: {va:g} {ua} versus {vb:g} {ub}. A policy "
                                f"parameter of this kind has one value at a time, so the two "
                                f"statements cannot both describe current policy."
                            ),
                            resolution=self._which_governs(earlier, later),
                            detector="quantity comparison on shared topics",
                        ))
        return out

    # -- detector 4: reality changed without a decision record -------------
    def _unratified_change(self) -> list[Contradiction]:
        out: list[Contradiction] = []
        gaps = [c for c in self.claims if _NO_FORMAL_DECISION.search(c.text)]
        decisions = [c for c in self.claims if c.claim_type is ClaimType.DECISION]
        for gap in gaps:
            for dec in decisions:
                if dec.doc_id == gap.doc_id:
                    continue
                if len(set(gap.topics) & set(dec.topics)) < 2:
                    continue
                if (dec.date or date.min) > (gap.date or date.min):
                    continue      # the decision is newer; that is detector 2's job
                out.append(Contradiction(
                    contradiction_id=_cid("unratified", dec.claim_id, gap.claim_id),
                    kind="unratified_change",
                    severity="high",
                    confidence=0.8,
                    claim_a=_ev(dec),
                    claim_b=_ev(gap),
                    why=(
                        f"{dec.doc_id} is a decision of record governing {sorted(set(dec.topics) & set(gap.topics))}. "
                        f"{gap.doc_id} reports that production behaviour changed on that same "
                        f"subject while stating that no decision document was filed. The conflict "
                        f"is not between two positions - it is that the operating state diverged "
                        f"from the governing record with nothing revoking it. Anyone reading the "
                        f"decision log alone would describe production incorrectly."
                    ),
                    resolution=(
                        f"Treat {dec.doc_id} as the standing decision and {gap.doc_id} as an "
                        f"unratified deviation. Either ratify the deviation or revert it; do not "
                        f"let the ambiguity persist in the record."
                    ),
                    detector="governance gap (change without decision record)",
                ))
        return out

    # -- detector 5: promise versus delivery -------------------------------
    def _commitment_breach(self) -> list[Contradiction]:
        out: list[Contradiction] = []
        commitments = [
            c for c in self.claims
            if _DEADLINE.search(c.text) and re.search(r"commit|told|would provide|will provide", c.text, re.I)
        ]
        slips = [c for c in self.claims if _DELAY.search(c.text)]
        for com in commitments:
            for slip in slips:
                if com.doc_id == slip.doc_id:
                    continue
                if len(set(com.topics) & set(slip.topics)) < 2:
                    continue
                if (slip.date or date.min) < (com.date or date.min):
                    continue
                out.append(Contradiction(
                    contradiction_id=_cid("commitment", com.claim_id, slip.claim_id),
                    kind="commitment_breach",
                    severity="medium",
                    confidence=0.8,
                    claim_a=_ev(com),
                    claim_b=_ev(slip),
                    why=(
                        f"{com.doc_id} records an external commitment with a date. {slip.doc_id}, "
                        f"dated {slip.date}, records that the same deliverable moved. The "
                        f"commitment as stated to the counterparty and the delivery state on "
                        f"record are inconsistent, and no amended commitment supersedes the "
                        f"original - so the corpus still carries a promise that was not met on "
                        f"its original terms."
                    ),
                    resolution=(
                        f"The operative fact is {slip.doc_id}. File an amended commitment so the "
                        f"record matches what the counterparty was actually told; until then, do "
                        f"not quote {com.doc_id} as the live commitment."
                    ),
                    detector="commitment deadline vs later status",
                ))
        return out

    # -- detector 6: internal decision against external norm ---------------
    def _external_divergence(self) -> list[Contradiction]:
        out: list[Contradiction] = []
        externals = [c for c in self.claims if c.authority.value == "external"]
        decisions = [c for c in self.claims if c.claim_type is ClaimType.DECISION]
        for ext in externals:
            ext_stances = stances_of(ext)
            for dec in decisions:
                dec_stances = stances_of(dec)
                shared_axes = ({s.axis.name for s in ext_stances}
                               & {s.axis.name for s in dec_stances})
                if not shared_axes:
                    continue
                axis_name = sorted(shared_axes)[0]
                ext_pos = {s.position for s in ext_stances if s.axis.name == axis_name}
                dec_pos = {s.position for s in dec_stances if s.axis.name == axis_name}
                if not ext_pos or not dec_pos or ext_pos == dec_pos:
                    continue
                shared = set(ext.topics) | {axis_name}
                out.append(Contradiction(
                    contradiction_id=_cid("external", ext.claim_id, dec.claim_id),
                    kind="external_divergence",
                    severity="low",
                    confidence=0.7,
                    claim_a=_ev(ext, caveat="external source - no authority over internal policy"),
                    claim_b=_ev(dec),
                    why=(
                        f"{ext.doc_id} states an external norm ({sorted(ext_pos)}) while the "
                        f"internal decision {dec.doc_id} adopts the opposite position "
                        f"({sorted(dec_pos)}) on {sorted(shared)}. This is not an institutional "
                        f"contradiction - an external publication does not bind the company - but "
                        f"it is a documented divergence from stated industry practice, which is a "
                        f"risk the decision implicitly accepts."
                    ),
                    resolution=(
                        f"{dec.doc_id} governs. Record the divergence as an accepted risk rather "
                        f"than leaving it to be rediscovered during diligence."
                    ),
                    detector="external reference vs internal decision",
                ))
        return out

    def _current_position(self, doc_ids: list[str]) -> str:
        entries = getattr(self.ledger, "entries", None)
        if not entries:
            return ""
        live = [entries[d] for d in doc_ids
                if d in entries and entries[d].status.value in {"ACTIVE", "CONTESTED"}]
        if not live:
            return "No live decision of record covers this; the conflict is unresolved."
        live.sort(key=lambda e: (AUTHORITY_RANK.get(e.authority, 0), e.date or date.min),
                  reverse=True)
        top = live[0]
        note = f" Caveat: {top.notes[0]}" if top.notes else ""
        return (f"As of the record, {top.doc_id} governs ({top.status.value}, "
                f"{top.authority.value}, {top.date}).{note}")

    # ---------------------------------------------------------------------
    def _which_governs(self, earlier: Claim, later: Claim) -> str:
        note = _authority_note(earlier, later)
        if later.claim_type is ClaimType.DECISION and earlier.claim_type is not ClaimType.DECISION:
            return (f"{later.doc_id} governs: it is a decision of record and {earlier.doc_id} is "
                    f"not. {note}")
        if earlier.claim_type is ClaimType.DECISION and later.claim_type is not ClaimType.DECISION:
            return (f"{earlier.doc_id} remains the decision of record; {later.doc_id} describes "
                    f"operating state that diverges from it rather than replacing it. {note}")
        return f"{later.doc_id} governs as the later record on the same subject. {note}"
