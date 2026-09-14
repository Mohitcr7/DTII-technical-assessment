# Known limitations and next engineering steps

## Known limitations

**1. Retrieval is lexical.** BM25 with hand-built synonym expansion. It handles this
corpus well and is deterministic — the same question returns the same evidence every
run, which is what makes the audit log worth keeping — but it will miss paraphrase
("who holds our keys" vs "custody provider") that an embedding model catches. The
interface (`ClaimIndex.search` → `list[Evidence]`) is the only thing consumers touch,
so hybrid retrieval is a drop-in.

**2. Stance axes are declarative configuration, not learned.** `stance.py` encodes
three axes (custody cardinality, retention period, EU region). A conflict on a
proposition family with no axis is caught only by the generic numeric, commitment and
governance-gap detectors. This is a deliberate trade: a deterministic detector that
misses is recoverable; a probabilistic one that fires inconsistently on institutional
memory is not. The intended path is model-*proposed*, human-accepted axes — the model
suggests a candidate axis, a person adds it, and comparison stays deterministic.

**3. Document authority is self-asserted.** `authority: board` is a frontmatter field.
Nothing authenticates who filed a document. This is the largest real-world gap and it
is not an AI problem — see next step #1.

**4. Injection heuristics are a filter, not a boundary.** A plausible poisoned document
that trips no heuristic still enters retrieval. The architectural controls (document
text never reaches the planner; no path from text to tool selection; human approval for
consequential acts) are what actually hold. The heuristics buy detection and taint
propagation, not immunity.

**5. Dates are document-level.** A claim inherits its document's date. A document that
describes events across several months gets one timestamp, which coarsens the
"what governed when" reasoning.

**6. No multi-tenant or field-level sensitivity model.** Every claim is equally
visible to every caller. A real deployment needs per-document sensitivity labels so an
outbound draft can be refused on content grounds, not only on approval grounds.

**7. Single-process, in-memory index.** The corpus is loaded at startup; there is no
incremental ingestion, no concurrency control on the action store beyond
last-write-wins, and no horizontal scaling. Correct for 18 documents, wrong for 18,000.

**8. The deterministic path composes extractively.** With no API key, answers are the
source sentences with their labels and citations. That is honest and unhallucinatable,
but it is not synthesis — it will read as terse next to a hosted-model answer.

**9. Contradiction clustering is by axis/kind.** Two genuinely distinct issues that
share an axis would be merged into one cluster with supporting pairs. Acceptable here;
it would need a subject key (which vendor, which policy) at larger scale.

---

## Recommended next three engineering steps

### 1. Signed ingestion with real provenance
Replace self-asserted frontmatter with an ingestion pipeline that records *who* filed
each document, *from which system*, and *with what authority*, cryptographically
bound. Board minutes come from the board tool; a Slack export carries Slack's identity
and Slack's (low) authority; an unattributed upload is quarantined by default rather
than trusted by default.

*Why first:* it closes the largest attack surface (§2 and §6 of the threat model),
converts `AUTHORITY_RANK` from a convention into a checkable fact, and is a
prerequisite for anything else being trustworthy. Everything downstream — ledger
status, conflict resolution, quarantine — already consumes `authority` and `doc_id`,
so this is an ingestion-layer change, not a redesign.

### 2. Hybrid retrieval with a claim-level evaluation set
Add embedding retrieval alongside BM25 with reciprocal-rank fusion, and — the part
that matters more — build a labelled evaluation set over this corpus: ~60 questions
with the claim ids that should be retrieved, including the adversarial ones
("what's our custody policy" must surface DOC-10 *and* DOC-02's governance gap). Gate
retrieval changes on it in CI.

*Why second:* it is the only capability where the current implementation is measurably
weaker than the state of the art, and without an evaluation set any change to ranking
is a guess. Building the eval also surfaces the contradiction-detection recall gaps,
which is the other place this system could quietly under-perform.

### 3. Durable, externally anchored audit and action store
Move `audit.jsonl` and `actions.jsonl` into a transactional append-only store with
idempotency keys on action execution, and periodically anchor the audit chain head
somewhere the application cannot write. Add a reconciliation job that verifies the
chain on a schedule and alerts on a break.

*Why third:* the hash chain already gives tamper-evidence for anything short of a
full rewrite, and the anchor is what closes that last gap (§9 of the threat model).
Idempotency on execution also removes the one remaining correctness risk in the action
path — a retried execution after a crash between `EXECUTED` and the audit write.

---

### Deliberately not next

- **A larger agent swarm.** More subagents is not more judgement. The three that exist
  (research, red team, technical) cover the shapes of question this corpus contains.
- **Fine-tuning a classifier.** The rule-based classifier is auditable — every label
  carries the trigger that produced it. Trading that for a few points of accuracy on a
  46-claim corpus is a bad exchange in a system whose value is being checkable.
- **Nicer UI.** Explicitly out of scope for this assessment, and the console already
  exposes every control path including the approval queue and the audit chain.
