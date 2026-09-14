---
doc_id: DOC-09
title: "Incident Report: ColdVault Outage"
doc_type: incident
source: "Postmortem"
date: 2026-04-18
declared_status: null
authority: engineering
topics: [incident, coldvault, outage, availability]
---

ColdVault experienced a regional HSM cluster failure lasting 6 hours and 12 minutes on April 17, 2026. All Veritas Chain signing operations were unavailable during this window.

Root cause: ColdVault's own infrastructure issue, not related to our integration.

Action item: evaluate secondary custody provider (see DOC-02).
