---
doc_id: DOC-07
title: "Follow-up: EU Latency Investigation"
doc_type: analysis
source: "Engineering Notes"
date: 2026-05-10
declared_status: null
authority: engineering
topics: [latency, eu, frankfurt, region, sla]
---

We pulled 3 weeks of latency logs for EU-based signing requests. Average latency was 340ms higher than US requests, consistent with the round-trip to us-east-1.

This supports the hypothesis raised in DOC-03, but we have not yet decided to open a Frankfurt region — this is still a recommendation, not a decision.
