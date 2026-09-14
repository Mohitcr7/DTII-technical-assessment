# What this Founder Agent must never be permitted to do autonomously

> Assessment §5.

## The principle

The line is not "risky vs. safe", and it is not about how good the model gets. It is
this:

> **The agent may never autonomously perform an act that creates an obligation,
> destroys the ability to reconstruct what happened, or asserts institutional
> authority the record does not contain.**

Three different reasons sit underneath that, and they are worth separating because
they fail in different ways and do not get fixed by the same improvements.

**1. Irreversibility.** An email to a bank's compliance team cannot be recalled. Once
an external party has read it, the company's position is what they read, not what was
meant. Autonomy is only tolerable where a mistake can be corrected more cheaply than
it costs. The relevant question is never "how confident is the model" but "what is
the cost of being wrong, and who pays it".

**2. Accountability that cannot be delegated.** When Veritas Chain tells Northbridge
Bank something, a *person* is making a representation on behalf of the company. A
model cannot hold that accountability — not because it is unreliable, but because
accountability is a relationship between people and institutions. Automating the
keystroke does not transfer the responsibility; it only removes the person who was
supposed to be exercising it. This reason does not weaken as models improve.

**3. Epistemic authority the record does not grant.** This corpus contains the exact
trap: DOC-02 changed production while explicitly noting that no decision document was
filed. An agent that treats "what is true in production" as "what the company decided"
manufactures institutional authority nobody granted. The agent's job is to *report the
state of the record, including its gaps* — never to close a gap by choosing an answer.

---

## The specific prohibitions

### 1. Any irreversible communication with an external party
Email, message, filing, attestation, commitment, or anything a counterparty could
reasonably treat as the company's position — to a customer, bank, regulator, partner
or investor. **Why:** all three reasons at once. In this corpus the agent can draft a
Northbridge attestation from DOC-05 and DOC-11 perfectly well; it must not send it,
because "we confirm no unauthorized key access occurred" is a representation to a
bank's compliance function, and DOC-11's evidence is one internal status note.

*Implemented:* `external_email.send` has `requires_human_approval=True` and no code
path to execution outside `ActionGateway`.

### 2. Recording, amending or retiring a decision of record
The agent may propose a decision document. It must never write one. **Why:** the
decision log is the company's memory of its own authority. An agent that can write to
it can, over time, launder its own inferences into institutional history — and the
corruption is invisible precisely because the log is what everyone checks. DOC-02 is
this failure without an agent involved; adding an agent that can file records makes it
faster and harder to see.

### 3. Resolving a contradiction it has detected
The agent must surface DOC-01 vs DOC-02 vs DOC-10 and say which record governs *and on
whose authority*. It must never mark one superseded, retire one, or pick a winner where
the record does not. **Why:** reversing a board decision requires board authority.
"Recency plus confidence" is not authority, and a system that quietly resolves conflicts
removes exactly the signal a founder needs — that the institution disagrees with itself.

### 4. Changing its own permissions, tool grants, or authorization rules
No self-modification of `allowed_roles`, of `requires_human_approval`, of the approver
credential, or of the audit configuration. **Why:** a capability model an agent can edit
is not a capability model. This is also the standard prompt-injection payoff: the
attacker's goal is rarely the action itself, it is the grant.

### 5. Deleting, editing or truncating the audit log
Append-only, always, including its own records — including embarrassing ones.
**Why:** the log is what makes every other control auditable rather than merely
claimed. An agent that can edit history can make any prior violation disappear, which
converts every other guarantee in this document into a hope.

### 6. Spending money, signing, or exercising a production credential
Procurement, contracts, key-custody operations, production signing. **Why:**
irreversible, externally binding, and in this domain the signing key *is* the company.
DOC-04 puts private key material inside the HSM boundary; nothing about an agent should
ever create a reason to move it.

### 7. Asserting a hypothesis, inference or recommendation as a decision or fact
The category boundary is a prohibition, not a preference. DOC-03 is a founder's
untested hunch; DOC-07 measured 340ms and explicitly declined to decide. An agent that
reports "we're opening a Frankfurt region" has not made a phrasing error — it has
invented a decision, and someone will act on it.

*Implemented:* rule-based classification with explicit vetoes, labels propagated
through retrieval into each answer segment, and segments labelled by their weakest
supporting evidence.

### 8. Speaking for the founder in the first person
No "we have decided", no signature, no persona. **Why:** the value of the founder's
word is that a person stood behind it. An agent that impersonates that spends the
credibility without the person knowing.

---

## What it *should* do autonomously

Drawing the line usefully means being clear about the other side of it, or the system
becomes a confirmation dialog with extra steps:

- Retrieve, cite, classify, and say UNKNOWN when the record is silent.
- Detect contradictions and explain why they conflict.
- Identify which record governs, with its status and authority, and flag when a
  proposal cuts against it.
- Draft anything at all — emails, memos, attestations, decision proposals — and
  present them for a human decision, with the evidence and the caveats attached.
- Delegate to subordinate agents, including a red team pointed at its own conclusion.
- Log everything.

**The agent's job is to make the founder's judgement better-informed and faster. It is
not to have that judgement.**

---

## The load-bearing part

Every prohibition above is enforced in code, not in a system prompt:

| Prohibition | Enforcement |
|---|---|
| No external send | `requires_human_approval`; no execute path outside `ActionGateway`; principal-kind check first |
| No self-approval | `approve()` rejects non-human principals before reading the action |
| No payload swap after approval | approval bound to `sha256` of the canonical payload, re-derived at execution |
| No stale approval | TTL expiry on pending actions |
| No capability escalation | static per-role grants; unknown tools rejected at the boundary |
| No history rewriting | append-only, hash-chained, `fsync`ed before the action proceeds |
| No category conversion | classification vetoes; labels propagate; weakest-evidence labelling |
| No fabrication | citation validation; extractive floor; UNKNOWN below the evidence threshold |

A prohibition that exists only in a prompt is a suggestion made to a probabilistic
system, in the same channel an attacker writes in. If the system prompt were deleted
tomorrow, every prohibition on this page would still hold.
