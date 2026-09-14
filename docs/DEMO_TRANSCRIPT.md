# Demo transcript — `claude-haiku-4-5`

Verbatim output of `./run.sh demo` with `ANTHROPIC_API_KEY` set and
`FA_ANTHROPIC_MODEL=claude-haiku-4-5`. Prose is model-written; every citation,
label, decision status, contradiction, refusal and audit event is computed in code
and is identical without a key. Finding lines are truncated by the CLI at 150 chars.

```text

============================================================================
2.1  KNOWLEDGE RETRIEVAL - answers carry sources; thin evidence returns UNKNOWN
============================================================================

Q: What signing algorithm and key custody boundary do we use?
verdict: ANSWERED   plan=decision_check provider=anthropic trace=tr_902879d3406749c2
  [FACT] Veritas Chain uses ECDSA P-256 for all production signing operations.  ['DOC-04#c1']
  [FACT] The key custody boundary is the custody provider's HSM, where key generation occurs exclusively and private key material never leaves.  ['DOC-04#c2']
  [DECISION] ColdVault Inc. is designated as the exclusive key-custody provider for all production signing keys.  ['DOC-01#c1']
  ! DOC-01 is contested by DOC-02.
  ! DOC-02 is SUPERSEDED by DOC-10 - historical, not current policy.

Q: What is our Series A valuation?
verdict: UNKNOWN   plan=lookup provider=anthropic trace=tr_9fa9ab9a68164321
  ? The supplied document set does not contain material that answers this.
  ? No document in the set mentions the subject of the question.
  ? To answer it, the corpus would need a record stating this directly.
  ! Answered UNKNOWN rather than inferring from weakly related material.

============================================================================
2.2  DECISION RETRIEVAL - governing record, status, source, rationale, conflict
============================================================================
governing : DOC-10 [ACTIVE] board 2026-07-30
source    : Board Meeting Minutes (excerpt)
decision  : The board reaffirmed the original vendor strategy: Veritas Chain will maintain ColdVault as its sole, exclusive custody provider going forward, citing cost discipline and integration simplicity. KeyForge integration should be wound down over the next two months.
rationale : citing cost discipline and integration simplicity
history   : [('DOC-02', 'SUPERSEDED'), ('DOC-01', 'ACTIVE')]

conflict with your proposal (high):
  The proposal takes position 'multiple' on how many custody providers hold production signing keys, while DOC-10 (ACTIVE, board, 2026-07-30) holds 'single'. Exclusivity is a cardinality claim about the same function at the same time: 'exclusive provider' means at most one. A second provider running live in production for that same function makes the exclusivity claim false. The two statements are not different words for one arrangement - they describe arrangements that cannot both hold. Adopting the proposal requires reversing DOC-10, which is a decision for board-level authority, not an implementation detail.

============================================================================
2.3  CONTRADICTION DETECTION - why they conflict, not that words differ
============================================================================

[high] How many custody providers govern production signing keys  ['DOC-01', 'DOC-02', 'DOC-06', 'DOC-10']
  DOC-01#c1 Decision: Veritas Chain will use ColdVault Inc. as our exclusive key-custody provider for all production signing keys, effective immediately.
  DOC-02#c2 Both providers are now live in production.
  why: Both statements take a position on the same axis: how many custody providers hold production signing keys. DOC-01 (2026-01-12) asserts 'single' - exactly one provider is authorised for this function. DOC-02 (2026-06-03) asserts 'multiple' - two or more providers serve this function concurrently. Exclusivity is a cardinality claim about the same function at the same time: 'exclusive provider' means at most one. A second provider running live in production for that same function makes the exclusivity claim false. The two statements are not different words for one arrangement - they describe arrangements that cannot both hold.
  resolution: DOC-01 remains the decision of record; DOC-02 describes operating state that diverges from it rather than replacing it. DOC-02 is later but carries lower authority (engineering vs founder), so recency alone does not settle it.
  today: As of the record, DOC-10 governs (ACTIVE, board, 2026-07-30).
  detector: stance axis: custody_vendor_cardinality; +8 supporting pair(s)

[high] Production changed without a decision record  ['DOC-01', 'DOC-02']
  DOC-01#c1 Decision: Veritas Chain will use ColdVault Inc. as our exclusive key-custody provider for all production signing keys, effective immediately.
  DOC-02#c4 No formal decision document was filed for this change; it was rolled out as part of the general infra sprint.
  why: DOC-01 is a decision of record governing ['coldvault', 'custody', 'keyforge', 'vendor']. DOC-02 reports that production behaviour changed on that same subject while stating that no decision document was filed. The conflict is not between two positions - it is that the operating state diverged from the governing record with nothing revoking it. Anyone reading the decision log alone would describe production incorrectly.
  resolution: Treat DOC-01 as the standing decision and DOC-02 as an unratified deviation. Either ratify the deviation or revert it; do not let the ambiguity persist in the record.
  today: As of the record, DOC-01 governs (ACTIVE, founder, 2026-01-12). Caveat: Contested in practice by DOC-02 (2026-06-03), which changed production behaviour without filing a decision record.
  detector: governance gap (change without decision record); +0 supporting pair(s)

[medium] External commitment not met on its original terms  ['DOC-15', 'DOC-16']
  DOC-15#c1 Founder told design partner (Halcyon Systems) that Veritas Chain would provide API sandbox access by end of May 2026 for their integration testing.
  DOC-16#c1 Sandbox access for Halcyon Systems was delayed to mid-June due to unrelated infra work.
  why: DOC-15 records an external commitment with a date. DOC-16, dated 2026-05-29, records that the same deliverable moved. The commitment as stated to the counterparty and the delivery state on record are inconsistent, and no amended commitment supersedes the original - so the corpus still carries a promise that was not met on its original terms.
  resolution: The operative fact is DOC-16. File an amended commitment so the record matches what the counterparty was actually told; until then, do not quote DOC-15 as the live commitment.
  today: No live decision of record covers this; the conflict is unresolved.
  detector: commitment deadline vs later status; +0 supporting pair(s)

[low] Policy superseded in the record  ['DOC-14', 'DOC-17']
  DOC-17#c1 [SUPERSEDED by DOC-14] Original draft proposed 3-year log retention.
  DOC-14#c1 Decision: All signing request logs will be retained for 7 years to meet anticipated regulatory requirements, even though no current regulation mandates this for our jurisdiction.
  why: DOC-17 and DOC-14 set the same policy to different values. DOC-17 carries an explicit supersession marker naming DOC-14, so the corpus itself records that the earlier position is no longer in force. The conflict is real but already resolved in the record.
  resolution: DOC-14 governs. DOC-17 is retained as history and must not be cited as current policy.
  today: As of the record, DOC-14 governs (ACTIVE, founder, 2026-03-01).
  detector: frontmatter supersession marker; +0 supporting pair(s)

[low] Internal decision diverges from stated industry practice  ['DOC-01', 'DOC-08', 'DOC-10']
  DOC-08#c1 Industry best practice increasingly favors multi-region, multi-vendor HSM redundancy for institutions handling >$10M in daily signed transaction volume, to avoid correlated vendor-specific outages.
  DOC-10#c1 The board reaffirmed the original vendor strategy: Veritas Chain will maintain ColdVault as its sole, exclusive custody provider going forward, citing cost discipline and integration simplicity.
  why: DOC-08 states an external norm (['multiple']) while the internal decision DOC-10 adopts the opposite position (['single']) on ['custody_vendor_cardinality', 'hsm', 'industry', 'multi-vendor', 'redundancy']. This is not an institutional contradiction - an external publication does not bind the company - but it is a documented divergence from stated industry practice, which is a risk the decision implicitly accepts.
  resolution: DOC-10 governs. Record the divergence as an accepted risk rather than leaving it to be rediscovered during diligence.
  today: As of the record, DOC-10 governs (ACTIVE, board, 2026-07-30).
  detector: external reference vs internal decision; +2 supporting pair(s)

============================================================================
2.4  CLASSIFICATION - every claim keeps its epistemic label
============================================================================
{'DECISION': 4, 'FACT': 28, 'INFERENCE': 7, 'HYPOTHESIS': 5, 'UNKNOWN': 2}
  DOC-01#c1    DECISION    (explicit 'Decision:' marker)
               Decision: Veritas Chain will use ColdVault Inc. as our exclusive key-custody provider fo
  DOC-03#c1    HYPOTHESIS  (self-labelled hypothesis)
               Hypothesis (untested): I suspect our EU customers are seeing higher signing latency beca
  DOC-07#c3    INFERENCE   (evidence-to-conclusion link)
               This supports the hypothesis raised in DOC-03, but we have not yet decided to open a Fra
  DOC-11#c1    FACT        (reported past event)
               First quarterly attestation report for Northbridge Bank (per commitment in DOC-05) was d
  DOC-10#c3    UNKNOWN     (no epistemic marker matched)
               This directly reverses the multi-custody rollout described in DOC-02, though DOC-02 is n

Note DOC-07#c3: mentions a hypothesis but is INFERENCE - reporting a hypothesis is not holding one.

============================================================================
2.5  AGENT DELEGATION - parent delegates, subordinates return typed results
============================================================================

redteam  status=ok confidence=0.8 provider=anthropic/claude-haiku-4-5-20251001
  task      : Should we add KeyForge as a second custody provider?
  summary   : The strongest objection is that the board has explicitly reaffirmed ColdVault as the sole, exclusive custody provider, rejecting the dual-provider approach on grounds of cost discipline and integration simplicity. Adding KeyForge would directly contradict this active board decision. Second, custody costs have already ballooned 40% since implementing the dual-provider model, and returning to a single provider was the board's stated rationale for cost control. Third, ColdVault alone has demonstrated sufficient security rigor, passing internal review with no critical findings and maintaining current SOC 2 Type II certification, so the risk-reduction argument for a second provider has been weighed and rejected by governance. Finally, the earlier document recommending KeyForge as secondary provider has been superseded, indicating the organization has already evaluated and decided against this path.
  finding   : [BLOCKING] The proposal takes position 'multiple' on how many custody providers hold production signing keys, while DOC-10 (ACTIVE, board, 2026-07-30)
  finding   : [STALE] Cites superseded records: DOC-02#c1 (DOC-02)
  finding   : [CONTESTED RECORD] The supplied material takes more than one position (['multiple', 'single']). Any answer must say which one governs, not average the

research  status=ok confidence=0.9 provider=anthropic/claude-haiku-4-5-20251001
  task      : Should we add KeyForge as a second custody provider?
  summary   : The record establishes a decision to use ColdVault Inc. as the exclusive custody provider, justified by measured facts that ColdVault passed security review with no critical findings and maintains current SOC 2 Type II certification, despite being 15% more expensive than KeyForge. History shows that KeyForge was briefly added as a secondary provider to reduce single-vendor risk, which increased custody spend by 40%, but this arrangement has been superseded by a board decision to return to ColdVault as the sole provider, citing cost discipline and integration simplicity. The question of whether to add KeyForge is already closed by the record: the current decision is against it.
  finding   : [DECISION] Decision: Veritas Chain will use ColdVault Inc. as our exclusive key-custody provider for all production signing keys, effective immediatel
  finding   : [DECISION] The board reaffirmed the original vendor strategy: Veritas Chain will maintain ColdVault as its sole, exclusive custody provider going forw
  finding   : [FACT] Rationale: ColdVault's HSM cluster passed our internal security review with no critical findings, and their SOC 2 Type II report is current. (D

============================================================================
2.6  HUMAN AUTHORIZATION - prepared, then blocked until a human approves
============================================================================
prepared  : act_b67625415de1  status=PENDING_HUMAN_AUTHORIZATION
intent    : Send an external email to compliance@northbridge.example summarising the position of record in response to: "Send Northbridge Bank our current custody position of record". Irreversible once sent.
hash      : e0fe96cb0aa2d8581062770ede90f48f62c6659dd8d0cd70708502722e2f38da

attempt 1 - the agent tries to approve its own action
  refused: only a human principal may approve an action

attempt 2 - execute without approval
  refused: cannot execute: action is PENDING_HUMAN_AUTHORIZATION, not APPROVED

attempt 3 - a human approves, then the payload is tampered with
  refused: payload changed after approval; execution refused

============================================================================
2.7  AUDITABILITY - the whole interaction, reconstructed from the log
============================================================================
trace tr_21b270bc95334b54: 7 events
  #522  05:11:25  founder                      user_request
  #523  05:11:27  retrieval                    retrieval
  #524  05:11:27  knowledge_service            model_call
  #525  05:11:27  orchestrator                 plan
  #526  05:11:30  redteam                      delegation
  #527  05:11:33  research                     delegation
  #528  05:11:33  orchestrator                 response

chain verification: {'ok': True, 'records': 540, 'head': 'aa2edba09ab917dbe2a5bd50163a0a9cabb0d3fc53e2f955529a680ccf80d822'}
Secrets are redacted before the write, so the log cannot leak them later.
```
