"""Decision ledger (assessment 2.2).

A founder asking "have we decided this already?" needs four things the raw
documents do not give them: which record governs *now*, what its status is,
how it got there, and whether what they are about to propose cuts against it.

The ledger therefore holds more than decision documents. A change that
happened without a decision record (DOC-02) is a first-class entry with status
INFORMAL, because leaving it out is how a decision log drifts away from
production reality.
"""

from __future__ import annotations

import re
from datetime import date

from .schemas import (
    AUTHORITY_RANK,
    Authority,
    Claim,
    ClaimType,
    ConflictAssessment,
    DecisionLookup,
    DecisionStatus,
    Document,
    GoverningDecision,
)
from .stance import stances_of

_INFORMAL = re.compile(
    r"no formal decision document was filed|no decision (document )?was (filed|made)", re.I)
_RATIONALE = re.compile(r"\b(rationale\s*:|citing|on the grounds|to meet|justifies)\b", re.I)


class DecisionLedger:
    def __init__(self, documents: list[Document]) -> None:
        self.documents = {d.doc_id: d for d in documents}
        self.entries: dict[str, GoverningDecision] = {}
        self._build()

    # -- construction ------------------------------------------------------
    def _build(self) -> None:
        for doc in self.documents.values():
            decision_claims = [c for c in doc.claims if c.claim_type is ClaimType.DECISION]
            informal = any(_INFORMAL.search(c.text) for c in doc.claims)
            # A document filed as a decision belongs in the ledger even when
            # its sentences no longer read as one - that is exactly the shape
            # of a superseded record, and dropping it would break the history
            # chain a founder needs to see.
            if not decision_claims and not informal and doc.doc_type != "decision":
                continue

            body = decision_claims or [c for c in doc.claims if stances_of(c)] or doc.claims[:1]
            decision_text = " ".join(c.text for c in body)
            rationale = next(
                (c.text for c in doc.claims
                 if _RATIONALE.search(c.text) and c.text not in decision_text),
                None,
            )
            self.entries[doc.doc_id] = GoverningDecision(
                doc_id=doc.doc_id,
                title=doc.title,
                status=DecisionStatus.INFORMAL if (informal and not decision_claims) else DecisionStatus.ACTIVE,
                source=doc.source,
                date=doc.date,
                authority=doc.authority,
                decision_text=decision_text,
                rationale=rationale,
                claim_ids=[c.claim_id for c in body],
                supersedes=list(doc.supersedes),
                superseded_by=doc.superseded_by,
            )

        self._resolve_statuses()

    def _resolve_statuses(self) -> None:
        # 1. Markers the corpus states outright always win.
        for entry in self.entries.values():
            doc = self.documents[entry.doc_id]
            if doc.declared_status == "SUPERSEDED" or doc.superseded_by:
                entry.status = DecisionStatus.SUPERSEDED
                entry.notes.append(
                    f"Superseded in the record by {doc.superseded_by or 'a later document'}.")
            for older in doc.supersedes:
                if older in self.entries:
                    self.entries[older].status = DecisionStatus.SUPERSEDED
                    self.entries[older].superseded_by = doc.doc_id

        # 2. Derived reversal / contest, by comparing stances across entries.
        for a_id, a in self.entries.items():
            for b_id, b in self.entries.items():
                if a_id >= b_id:
                    continue
                axis, pos_a, pos_b = self._shared_axis(a, b)
                if axis is None or pos_a == pos_b:
                    if axis is not None and a.status is not DecisionStatus.SUPERSEDED \
                            and b.status is not DecisionStatus.SUPERSEDED:
                        self._note_reaffirmation(a, b)
                    continue
                earlier, later = self._chronological(a, b)
                if later.status is DecisionStatus.SUPERSEDED:
                    continue
                if later.status is DecisionStatus.INFORMAL:
                    # A change made without a decision record does not overturn
                    # the decision; it contests it, and that gap is the finding.
                    earlier.contested_by.append(later.doc_id)
                    earlier.notes.append(
                        f"Contested in practice by {later.doc_id} ({later.date}), which changed "
                        f"production behaviour without filing a decision record.")
                elif earlier.status is DecisionStatus.INFORMAL:
                    earlier.status = DecisionStatus.SUPERSEDED
                    earlier.superseded_by = later.doc_id
                    earlier.notes.append(
                        f"Reversed by {later.doc_id} ({later.authority.value}, {later.date}).")
                elif AUTHORITY_RANK.get(later.authority, 0) >= AUTHORITY_RANK.get(earlier.authority, 0):
                    earlier.status = DecisionStatus.SUPERSEDED
                    earlier.superseded_by = later.doc_id
                    earlier.notes.append(
                        f"Reversed by {later.doc_id} on {later.date} "
                        f"({later.authority.value} authority).")
                else:
                    earlier.status = DecisionStatus.CONTESTED
                    earlier.contested_by.append(later.doc_id)
                    earlier.notes.append(
                        f"{later.doc_id} takes the opposite position but carries lower authority "
                        f"({later.authority.value} vs {earlier.authority.value}); unresolved.")

    def _note_reaffirmation(self, a: GoverningDecision, b: GoverningDecision) -> None:
        earlier, later = self._chronological(a, b)
        if later.doc_id in earlier.notes:
            return
        earlier.notes.append(f"Reaffirmed by {later.doc_id} ({later.date}).")
        later.supersedes = sorted(set(later.supersedes) | {earlier.doc_id})

    def _shared_axis(self, a: GoverningDecision, b: GoverningDecision):
        sa = self._stances(a)
        sb = self._stances(b)
        shared = {s.axis.name for s in sa} & {s.axis.name for s in sb}
        if not shared:
            return None, None, None
        axis = sorted(shared)[0]
        return (
            axis,
            next(s.position for s in sa if s.axis.name == axis),
            next(s.position for s in sb if s.axis.name == axis),
        )

    def _stances(self, entry: GoverningDecision):
        doc = self.documents[entry.doc_id]
        return [s for c in doc.claims for s in stances_of(c)]

    @staticmethod
    def _chronological(a: GoverningDecision, b: GoverningDecision):
        return (a, b) if (a.date or date.min) <= (b.date or date.min) else (b, a)

    # -- query -------------------------------------------------------------
    def lookup(self, question: str, candidate_doc_ids: list[str]) -> DecisionLookup:
        """Find the governing decision behind a question, if one exists."""
        relevant = [self.entries[d] for d in candidate_doc_ids if d in self.entries]
        if not relevant:
            return DecisionLookup(question=question, found=False)

        # Pull in the rest of the lineage so history is complete even when
        # retrieval only surfaced one link of the chain.
        expanded = dict((e.doc_id, e) for e in relevant)
        for entry in list(expanded.values()):
            for related in entry.supersedes + entry.contested_by + (
                    [entry.superseded_by] if entry.superseded_by else []):
                if related in self.entries:
                    expanded.setdefault(related, self.entries[related])

        lineage = sorted(expanded.values(), key=lambda e: (e.date or date.min), reverse=True)
        governing = self._pick_governing(lineage)
        history = [e for e in lineage if governing is None or e.doc_id != governing.doc_id]

        return DecisionLookup(
            question=question,
            found=governing is not None,
            governing=governing,
            history=history,
            proposal_conflict=self.assess_proposal(question, governing),
        )

    @staticmethod
    def _pick_governing(lineage: list[GoverningDecision]) -> GoverningDecision | None:
        live = [e for e in lineage if e.status in {DecisionStatus.ACTIVE, DecisionStatus.CONTESTED}]
        if not live:
            return None
        live.sort(
            key=lambda e: (
                e.status is DecisionStatus.ACTIVE,
                AUTHORITY_RANK.get(e.authority, 0),
                e.date or date.min,
            ),
            reverse=True,
        )
        return live[0]

    def assess_proposal(
        self, proposal: str, governing: GoverningDecision | None
    ) -> ConflictAssessment:
        """Does what the user is proposing cut against the standing decision?"""
        if governing is None:
            return ConflictAssessment(conflicts=False, severity="none",
                                      explanation="No governing decision found for this subject.")

        probe = Claim(
            claim_id="proposal#0", doc_id="proposal", ordinal=0, text=proposal,
            claim_type=ClaimType.UNKNOWN, type_reason="user proposal",
            topics=[], authority=Authority.FOUNDER,
        )
        # A proposal is read non-assertively: we want the position it *would*
        # establish, so it can be compared with what is already decided.
        proposal_stances = stances_of(probe, assertive_only=False)
        if not proposal_stances:
            return ConflictAssessment(
                conflicts=False, severity="none",
                explanation="The question does not state a position that can be compared with the "
                            "standing decision; treat this as a lookup, not a proposal.")

        gov_stances = self._stances(governing)
        for ps in proposal_stances:
            for gs in gov_stances:
                if ps.axis.name != gs.axis.name or ps.position == gs.position:
                    continue
                return ConflictAssessment(
                    conflicts=True,
                    severity="high" if governing.status is DecisionStatus.ACTIVE else "medium",
                    explanation=(
                        f"The proposal takes position '{ps.position}' on {ps.axis.subject}, while "
                        f"{governing.doc_id} ({governing.status.value}, {governing.authority.value}, "
                        f"{governing.date}) holds '{gs.position}'. {ps.axis.incompatibility} "
                        f"Adopting the proposal requires reversing {governing.doc_id}, which is a "
                        f"decision for {governing.authority.value}-level authority, not an "
                        f"implementation detail."
                    ),
                    governing_claim_ids=governing.claim_ids,
                )
        return ConflictAssessment(
            conflicts=False, severity="none",
            explanation=f"The proposal is consistent with {governing.doc_id} as currently recorded.",
            governing_claim_ids=governing.claim_ids,
        )
