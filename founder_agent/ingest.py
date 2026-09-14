"""Corpus loading: markdown + frontmatter -> Documents -> Claims.

Claims, not documents, are the unit of retrieval and citation. A document can
hold a decision and an untested hypothesis in adjacent sentences; citing the
document would blur them together.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path

from .classify import Classifier
from .guards import scan_for_injection
from .schemas import Authority, Claim, ClaimType, Document

_FRONTMATTER = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)

# Sentence splitter that keeps "ColdVault Inc.", "OAuth 2.0", "P-256",
# "SOC 2 Type II" and "us-east-1" intact.
_ABBREV = r"(?<!\bInc)(?<!\bLtd)(?<!\bCo)(?<!\be\.g)(?<!\bi\.e)(?<!\bNo)(?<!\bvs)"
_SENT_SPLIT = re.compile(rf"{_ABBREV}(?<=[.!?])\s+(?=[A-Z\[])")


def _parse_scalar(raw: str):
    raw = raw.strip()
    if raw in {"null", "~", ""}:
        return None
    if raw.startswith("[") and raw.endswith("]"):
        inner = raw[1:-1].strip()
        if not inner:
            return []
        return [p.strip().strip('"\'') for p in inner.split(",")]
    if raw.startswith('"') and raw.endswith('"'):
        return raw[1:-1]
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
        return datetime.strptime(raw, "%Y-%m-%d").date()
    return raw


def _parse_frontmatter(block: str) -> dict:
    out: dict = {}
    for line in block.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        key, _, value = line.partition(":")
        out[key.strip()] = _parse_scalar(value)
    return out


def split_sentences(paragraph: str) -> list[str]:
    parts = [p.strip() for p in _SENT_SPLIT.split(paragraph.strip()) if p.strip()]
    return parts or ([paragraph.strip()] if paragraph.strip() else [])


class CorpusLoader:
    def __init__(self, corpus_dir: Path, classifier: Classifier | None = None) -> None:
        self.corpus_dir = corpus_dir
        self.classifier = classifier or Classifier()

    def load(self) -> list[Document]:
        docs = [self._load_one(p) for p in sorted(self.corpus_dir.glob("*.md"))]
        return [d for d in docs if d is not None]

    def _load_one(self, path: Path) -> Document | None:
        raw = path.read_text(encoding="utf-8")
        m = _FRONTMATTER.match(raw)
        if not m:
            return None
        meta = _parse_frontmatter(m.group(1))
        body = raw[m.end():].strip()

        authority_raw = str(meta.get("authority") or "engineering")
        try:
            authority = Authority(authority_raw)
        except ValueError:
            authority = Authority.ENGINEERING

        doc = Document(
            doc_id=str(meta.get("doc_id") or path.stem),
            title=str(meta.get("title") or path.stem),
            doc_type=str(meta.get("doc_type") or "note"),
            source=str(meta.get("source") or path.name),
            date=meta.get("date") if isinstance(meta.get("date"), date) else None,
            authority=authority,
            topics=list(meta.get("topics") or []),
            declared_status=meta.get("declared_status"),
            supersedes=list(meta.get("supersedes") or []),
            superseded_by=meta.get("superseded_by"),
            body=body,
        )
        doc.claims = self._to_claims(doc)
        self._propagate_document_trust(doc)
        return doc

    @staticmethod
    def _propagate_document_trust(doc: Document) -> None:
        """Trust is a property of the source, not of the sentence.

        If one passage in a document is trying to issue instructions, the
        document is attacker-influenced and its *other* sentences are no more
        trustworthy than that one - an attacker who can write paragraph three
        can write paragraph four. So the flag propagates to the whole document
        and the quarantine covers all of it.
        """
        triggered = sorted({f for c in doc.claims for f in c.injection_flags})
        if not triggered:
            return
        for claim in doc.claims:
            if not claim.injection_flags:
                claim.injection_flags = [f"tainted_source:{doc.doc_id}"]

    def _to_claims(self, doc: Document) -> list[Claim]:
        claims: list[Claim] = []
        ordinal = 0
        for paragraph in [p for p in doc.body.split("\n\n") if p.strip()]:
            for sentence in split_sentences(paragraph):
                ordinal += 1
                ctype, reason, conf = self.classifier.classify(sentence, doc_type=doc.doc_type)
                # A document whose declared status is SUPERSEDED cannot contain
                # a governing decision, whatever its sentences look like.
                if ctype is ClaimType.DECISION and doc.declared_status == "SUPERSEDED":
                    reason = f"{reason} (document declared SUPERSEDED)"
                claims.append(
                    Claim(
                        claim_id=f"{doc.doc_id}#c{ordinal}",
                        doc_id=doc.doc_id,
                        ordinal=ordinal,
                        text=sentence,
                        claim_type=ctype,
                        type_reason=reason,
                        type_confidence=conf,
                        topics=doc.topics,
                        date=doc.date,
                        authority=doc.authority,
                        doc_title=doc.title,
                        doc_source=doc.source,
                        injection_flags=scan_for_injection(sentence),
                    )
                )
        return claims
