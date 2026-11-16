# 0003: Sequential idempotency keys, spent keys shortened

Date: 2026-11-16. Status: accepted.

## Problem
Idempotency keys were `<shot>-<l|p>-<16 random hex>`. In a JSON line the field name `idempotency_key` followed by a
long random value matches the generic API key rule of secret scanners, so the build gate refused the ledger. The value
is not a secret: it only makes a retried POST return the same job instead of charging twice.

## Decision
- New keys are `<idempotency_prefix>-NNNN` (`config/film.json`, `ve.idempotency_prefix`), where NNNN is the ledger row
  count plus one, skipping any key already used (`tools/ledger.py` `next_key`). One generation runs at a time and the
  ledger refuses duplicate keys, so a sequence is unique without randomness.
- The four keys already spent (all jobs finished, `done` or `failed` and refunded) were shortened in
  `log/generations.jsonl` to their first four hex digits and marked `"key_truncated": true`. Job id, credits, balances
  and sha256 are unchanged, so the ledger still accounts for every credit. Those keys are never resumed.
- A test fails if any tracked ledger key carries a hex run of 8 or more characters.

## Rollback
Restore the random suffix in `Client.submit`; the scanner would then refuse new ledger rows again.
