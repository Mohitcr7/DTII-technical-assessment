---
doc_id: DOC-02
title: "Infrastructure Update: Multi-Custody Rollout"
doc_type: status_update
source: "Engineering All-Hands Notes"
date: 2026-06-03
declared_status: null
authority: engineering
topics: [custody, vendor, coldvault, keyforge, redundancy]
---

As part of Q2 infra hardening, we've onboarded KeyForge as a secondary custody provider alongside ColdVault to reduce single-vendor risk. Both providers are now live in production.

Note: This was driven by ColdVault's April outage (6 hours of signing downtime) — see incident report DOC-09.

No formal decision document was filed for this change; it was rolled out as part of the general infra sprint.
