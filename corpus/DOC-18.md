---
doc_id: DOC-18
title: "Technical Note: Rate Limiting"
doc_type: technical_note
source: "Engineering Wiki Export"
date: 2026-06-20
declared_status: null
authority: engineering
topics: [api, rate-limit, throughput]
---

Signing API is rate-limited to 500 requests/second per client, with burst allowance of 700/second for up to 30 seconds.
