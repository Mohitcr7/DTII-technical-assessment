# Founder Intelligence Agent

A working prototype of an institutional-memory agent for Veritas Chain Technologies,
built against the supplied 18-document set.

The document set is deliberately inconsistent: a founder decision, an engineering
rollout that quietly contradicts it, a board decision that reverses the rollout
without naming it, a superseded policy, two untested hypotheses, a commitment that
slipped, and an external article that disagrees with all of it. A retrieval system
that averages those into fluent prose is worse than no system at all, because it
launders an unratified deviation into "company policy". Everything below follows
from refusing to do that.

---

## Quickstart

```bash
cd founder-agent
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
```

Run the guided walkthrough of all seven capabilities:

```bash
.venv/bin/python -m founder_agent.cli demo
```

Run the web UI:

```bash
.venv/bin/python -m founder_agent.cli serve    # http://127.0.0.1:8000
```

Run the tests, including the attacks against our own controls:

```bash
.venv/bin/python -m pytest tests -q            # 62 tests
```

**No API key is required.** With `ANTHROPIC_API_KEY` or `OPENAI_API_KEY` set, the
system uses a hosted model to phrase answers and to add a second opinion in the
subagents. Without one it runs a deterministic path: answers are composed
extractively from the source sentences. Retrieval, classification, the decision
ledger, contradiction detection, delegation and every authorization control are
identical either way, because none of them live in a prompt. See
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md#4-changing-model-providers).

---

## The seven capabilities

| § | Capability | Where it lives | What it does that a naive version would not |
|---|---|---|---|
| 2.1 | Knowledge retrieval | `knowledge.py`, `retrieval.py` | Cites at claim level, not document level. Returns **UNKNOWN** with a description of the gap when evidence is thin, instead of composing something plausible. |
| 2.2 | Decision retrieval | `decisions.py` | Returns the governing record, its status, source, rationale, its history, and whether your proposal **conflicts** with it — plus who has the authority to overturn it. |
| 2.3 | Contradiction detection | `contradictions.py`, `stance.py` | Six detectors that explain *why* two statements are incompatible (shared proposition, incompatible positions), then cluster the pairs into the handful of issues a founder actually has. |
| 2.4 | Classification | `classify.py` | FACT / INFERENCE / HYPOTHESIS / DECISION / UNKNOWN, rule-first with a quotable trigger for every label. Explicit vetoes stop the two conversions that matter: recommendation → decision, and hypothesis → fact. |
| 2.5 | Agent delegation | `agents/` | Research, red-team and technical subagents with their own tool grants, fixed context, token budgets and typed results. Citations are validated against the claims the parent handed over. |
| 2.6 | Human authorization | `authorization.py` | Consequential actions can be *prepared* but have no code path to execution without a human principal presenting a credential the agent process never holds. Approval is bound to a hash of the exact payload. |
| 2.7 | Auditability | `audit.py` | Hash-chained append-only log. `reconstruct(trace_id)` returns request, retrieved context, model, delegations, tool request, output, human decision and resulting action. Secrets are redacted **before** the write. |

---

## What it looks like in practice

Ask: *"Should we add KeyForge as a second custody provider?"*

```
verdict: PARTIAL   plan=proposal_review provider=deterministic

governing decision: DOC-10 [ACTIVE] board 2026-07-30
  The board reaffirmed the original vendor strategy: Veritas Chain will maintain
  ColdVault as its sole, exclusive custody provider going forward...

  CONFLICT (high): The proposal takes position 'multiple' on how many custody
  providers hold production signing keys, while DOC-10 (ACTIVE, board, 2026-07-30)
  holds 'single'. Exclusivity is a cardinality claim about the same function at the
  same time... Adopting the proposal requires reversing DOC-10, which is a decision
  for board-level authority, not an implementation detail.

delegated -> redteam (blocking)
  • [BLOCKING] ...conflicts with DOC-10...
  • [STALE] Cites superseded records: DOC-02#c1 (DOC-02)
  • [CONTESTED RECORD] The supplied material takes more than one position
    (['multiple', 'single']). Any answer must say which one governs, not average them.

contradiction: [high] How many custody providers govern production signing keys
contradiction: [high] Production changed without a decision record
```

The last line is the finding that matters most and the one a similarity-search
system cannot produce: DOC-02 changed production while stating that *no decision
document was filed*. That is not two documents disagreeing — it is the operating
state diverging from the decision log with nothing revoking it.

---

## Contradictions found in the supplied set

| Severity | Issue | Documents | Detector |
|---|---|---|---|
| high | How many custody providers govern production signing keys | DOC-01, DOC-02, DOC-06, DOC-10 | stance axis: cardinality |
| high | Production changed without a decision record | DOC-01, DOC-02 | governance gap |
| medium | External commitment not met on its original terms | DOC-15, DOC-16 | commitment deadline vs later status |
| low | Policy superseded in the record (3-year → 7-year retention) | DOC-14, DOC-17 | explicit supersession marker |
| low | Internal decision diverges from stated industry practice | DOC-01, DOC-08, DOC-10 | external reference vs internal decision |

Equally important is what it does **not** report. DOC-05 (promise of quarterly
attestation) and DOC-11 (attestation delivered on time) are not a contradiction.
DOC-03's untested latency hypothesis is never reported as conflicting with a
decision, because a hypothesis and a decision are different kinds of statement —
that gate is asserted in `tests/test_contradictions.py`.

---

## Documentation

- **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)** — component diagram, data flow, and the answer to §4 (swapping model providers, adding email/calendar/GitHub/local models).
- **[docs/THREAT_MODEL.md](docs/THREAT_MODEL.md)** — §3: how I would attack this system, what stops each attack, and which protections are in code rather than in prompts.
- **[docs/AUTONOMY_BOUNDARY.md](docs/AUTONOMY_BOUNDARY.md)** — §5: what this agent must never do autonomously, and why.
- **[docs/LIMITATIONS.md](docs/LIMITATIONS.md)** — known limitations and the next three engineering steps.

---

## Design decisions worth defending

**Correctness logic is in code, not in prompts.** Classification, supersession,
contradiction detection and every authorization control are deterministic Python.
A model is used for phrasing and for a second opinion. This is not model
scepticism — it is that institutional memory needs the same answer every time and
an audit trail that means something, and a token predictor gives you neither.

**Claims, not documents, are the unit of retrieval.** DOC-07 contains a measured
fact, an inference, and an explicit statement that no decision was made. Citing
the document would blur all three. Each sentence carries its own id, epistemic
label, date and authority.

**The epistemic label is data that travels.** It is attached at ingestion, carried
through retrieval, and used to label each answer segment. An answer segment is
labelled by the *weakest* evidence holding it up, so a hypothesis cannot be
laundered into a fact by being summarised.

**The planner never sees document text.** Routing decisions use the user's question
plus structural metadata (document ids, epistemic labels, scores). No sentence in
the corpus can cause an agent to be spawned or a tool to be chosen.

**Trust is a property of the source.** If one passage in a document contains
instruction-shaped content, the whole document is quarantined. An attacker who can
write paragraph three can write paragraph four.

**Degrade, don't fail.** Every provider chain ends in a local deterministic floor.
A provider outage costs you prose quality, not the ability to answer or the
authorization controls.

---

## Project layout

```
corpus/                   18 source documents (markdown + frontmatter)
founder_agent/
  schemas.py              typed contracts shared by every layer
  ingest.py               documents -> claims, with trust propagation
  classify.py             FACT / INFERENCE / HYPOTHESIS / DECISION / UNKNOWN
  stance.py               proposition axes used to compare positions
  retrieval.py            BM25 over claims, dependency-free and deterministic
  knowledge.py            grounded answering + evidence discipline
  decisions.py            decision ledger: status, supersession, conflict
  contradictions.py       six detectors + clustering
  guards.py               injection heuristics, redaction, trust boundary
  authorization.py        the human-in-the-loop gate
  audit.py                hash-chained append-only log
  agents/                 orchestrator + research / redteam / technical
  llm/                    provider-neutral interface, routing, failover
  tools/                  capability-scoped tool registry
  api.py / cli.py         HTTP and terminal surfaces
ui/index.html             single-file console
tests/                    62 tests, including attacks on our own controls
```
