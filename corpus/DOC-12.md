---
doc_id: DOC-12
title: "Technical Note: API Authentication"
doc_type: technical_note
source: "Engineering Wiki Export"
date: 2026-02-02
declared_status: null
authority: engineering
topics: [api, auth, oauth, tokens, security]
---

All internal services authenticate to the signing API using short-lived OAuth 2.0 client-credential tokens (15-minute expiry). Token issuance is logged.
