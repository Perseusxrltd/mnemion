# Fair indexing dispatch — 20 October 2026

Source candidate: 4.35.0, migration `029_fair_indexing.sql`.

**18 real PostgreSQL cases passed** across the new dispatch checks and existing
reindex suite:

- Sixteen older source jobs yield the next turn to another space. A new Worker
  object retains the same persisted order; both spaces continue progressing.
- An organization with five active spaces alternates turns with another
  organization. Processing across both tenants does not grant either owner
  access to the other's memories.
- A newer purge overtakes older embedding jobs with no model generation
  available, completes physical cleanup and retains its normal operation state.
- Two simultaneous database transactions skip the other's locked organization
  and receive different job/lease identities. The second call does not wait for
  the first transaction to release its dispatch locks.
- An unavailable generation does not advance a queue, and the ordinary API
  database role cannot call the claim function.
- Existing active/candidate generation transitions, paused processing, cancelled
  candidates, indexing and retrieval checks passed unchanged.

The checks use deterministic fixture embeddings to verify dispatch and
authorization, not model quality or a production latency target. No provider or
paid-model request is involved. A monotonic database sequence makes dispatch
independent of wall-clock corrections.

**28 schema-upgrade preflight cases passed**, including all supported historical
schema fixtures and the immediately preceding 028 schema. The first preflight
caught the installed inventory treating the new NULL dispatch field as a changed
tenant. The corrected inventory supplies NULL only where the field is absent and
now also hashes complete space rows. It retains all actual candidate fields.
Deliberately changing either counter makes both inventory comparisons fail;
existing key and passage-history corruption checks also remain effective.

The [live 4.33 observation](2026-10-20-433-live-updates.md) supplied the actual
backlog that motivated the change. This source validation does not claim the
live host has been migrated. Native migration/recovery jobs, independent
artifact verification, publication and the guarded real-host upgrade remain
separate gates.
