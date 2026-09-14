---
doc_id: DOC-04
title: "Technical Note: Signing Protocol Overview"
doc_type: technical_note
source: "Engineering Wiki Export"
date: 2026-03-15
declared_status: null
authority: engineering
topics: [signing, ecdsa, hsm, protocol, logging]
---

Veritas Chain uses ECDSA P-256 for all production signing operations. Key generation occurs exclusively within the custody provider's HSM boundary; private key material never leaves the HSM.

All signing requests are logged with a request ID, timestamp, and requesting service identity.
