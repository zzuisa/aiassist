# Generated API types

This directory holds types generated from `specs/001-personal-life-os/contracts/openapi.yaml`.

The MVP hand-maintains `src/api/types.ts` (kept in sync with the OpenAPI contract);
CI runs an OpenAPI→TS generation step and diffs the output against the checked-in
types to catch drift (see `backend/tests/contract/test_schema_drift.py` for the
backend side of the same guard).

To regenerate locally once codegen is wired:

```bash
npx openapi-typescript ../../../specs/001-personal-life-os/contracts/openapi.yaml \
  -o src/api/generated/openapi.d.ts
```
