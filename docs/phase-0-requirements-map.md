# Phase 0 — Pocketful requirements and architecture map

Status: complete for the published kickoff package at source revision
`803560d2a678ace1414465c098eb0ab5380ffade`.

This note records understanding only. It does not choose an implementation stack,
define Pocketful-specific agent mandates, or authorize application code.

## Authoritative sources

- [Participant guide](https://github.com/band-ai/dark-factory-wearedevs/blob/803560d2a678ace1414465c098eb0ab5380ffade/docs/participant-guide.md)
- [Pocketful stage 1](https://github.com/band-ai/dark-factory-wearedevs/blob/803560d2a678ace1414465c098eb0ab5380ffade/pocketful/spec/stage-1.md)
- [Pocketful stage 2](https://github.com/band-ai/dark-factory-wearedevs/blob/803560d2a678ace1414465c098eb0ab5380ffade/pocketful/spec/stage-2.md)
- [Pocketful stage 3](https://github.com/band-ai/dark-factory-wearedevs/blob/803560d2a678ace1414465c098eb0ab5380ffade/pocketful/spec/stage-3.md)
- [Pocketful stage 4](https://github.com/band-ai/dark-factory-wearedevs/blob/803560d2a678ace1414465c098eb0ab5380ffade/pocketful/spec/stage-4.md)
- [Harness CLI](https://github.com/band-ai/dark-factory-wearedevs/blob/803560d2a678ace1414465c098eb0ab5380ffade/harness/cli.py)
- [Harness Docker driver](https://github.com/band-ai/dark-factory-wearedevs/blob/803560d2a678ace1414465c098eb0ab5380ffade/harness/docker_driver.py)
- [Offline submission check](https://github.com/band-ai/dark-factory-wearedevs/blob/803560d2a678ace1414465c098eb0ab5380ffade/harness/check.py)

The specifications are authoritative for product behavior. Shipped tests are partial
feedback and must not be treated as the requirements.

## Two systems, two kinds of evidence

### The factory

The factory is the reusable BAND team: separate seats plan, implement, attack, and
independently verify work. Its quality is demonstrated by generic mandates, complete
handoffs, reciprocal seat communication, evidence-backed rejection or acceptance,
traceable commits, and a room export.

Factory behavior belongs in mandates. Pocketful vocabulary, endpoints, fields, error
codes, and test cases belong in tasks, plans, ledgers, and verification artifacts.

### Pocketful

Pocketful is the staged service produced by the factory. Each `stage-N/` directory is a
complete service implementing that stage and every earlier stage, but no intentional
later-stage surface. A later stage extends a copied, accepted earlier stage; it does not
replace the earlier folder.

Hand-written stage code is ineligible. The submitted room and Git history must show that
the BAND seats produced and reviewed the implementation.

## Invariants spanning all stages

- Monetary values are exact integer minor units; floating-point money is unacceptable.
- Money moves only between existing wallets. The sum of wallet totals remains equal to
  the amount seeded by the last reset in current and historical views.
- No total or available balance may become negative, including transiently or under
  concurrent requests.
- Every multi-wallet or multi-record mutation is all-or-nothing.
- Required idempotency keys are scoped to the authenticated caller. A successful replay
  returns the original response and never repeats an effect.
- Concurrent conflicting requests must be equivalent to some valid serial order.
- Original receipts remain stable even when later stages add corrections, refunds, or
  new views of history.
- Imports replace state atomically and must preserve identities, credentials, tokens,
  monetary records, successful retry records, and stage-specific links.
- Every earlier-stage contract remains active in every later-stage folder.

## Stage progression

### Stage 1 — payments and settlements

Stage 1 establishes the HTTP-only product and the core ledger.

Product surface:

- Signup and login with non-expiring bearer tokens and hashed passwords.
- Wallet identity and balance through `GET /me`.
- Direct payments, payment requests, request payment/decline/cancel, bill splits, and a
  visibility-filtered activity feed.
- Operator settlements containing 1–32 transfers committed atomically using net wallet
  affordability rather than per-entry affordability.
- Unauthenticated reset, export, and import controls for deterministic fixtures and
  cross-process state transfer.

Core semantics:

- Payments debit and credit atomically.
- Pending requests may exceed current funds; funds are checked only when paying.
- Equal splits use deterministic quotient/remainder allocation in participant order;
  zero-valued shares are legal and shares always sum to the original amount.
- Five write paths are idempotent: payments, requests, request payment, splits, and
  settlements.
- Concurrent first use of one key produces one `201`, replaying callers receive `200`,
  and the mutation happens once.
- Export/import preserves accounts, password hashes, tokens, payments, requests,
  settlements, permissions, completed idempotency bodies, and original responses.
- Container restart durability is not required; export/import compatibility is.

Implementation implications to carry forward:

- Ledger mutation, idempotency claiming, and response capture must share one atomic
  transaction boundary.
- Stable opaque IDs and recorded timestamps are required because later stages add
  historical semantics without changing original receipts.
- Settlement membership must be stored explicitly for later batch-correction rules.

### Stage 2 — browser product and authorizations

Stage 2 keeps all Stage 1 behavior and adds a responsive consumer UI plus held funds.

Browser surface:

- Required routes cover the wallet, requests, split, signup, login, and authorizations.
- API and HTML share `/requests` and `/authorizations`, selected by `Accept: text/html`.
- Required `data-testid` hooks, human-formatted amounts, visible labels, keyboard focus,
  adequate contrast, responsive 375-pixel behavior, and considered empty/loading/error
  states form part of the contract.
- Successful actions refresh relevant state without a manual reload.
- Latest refresh wins when reads return out of order.
- A lost payment response is an uncertain outcome, not a confirmed failure. Retrying
  uses the same key and body and must move money once.

Ledger additions:

- Authorizations reserve available money without changing wallet totals.
- `balance = total`; `available = total - held`; available never becomes negative.
- Captures move reserved money, may be partial and nonfinal, and preserve ordered capture
  links. Final capture releases any remainder.
- Void and clock expiry release only the remaining hold.
- Payments, request payments, and settlements now check available rather than total funds.
- Authorizations and captures raise the idempotent write-path count from five to seven.

Upgrade obligation:

- Stage 2 imports Stage 1 exports.
- Existing browser sessions remain signed in.
- Existing requests and pending idempotent retry identities remain usable after upgrade.
- An omitted authorization collection means none; derived available funds must remain
  correct for imported and seeded state.

### Stage 3 — effective history and immutable corrections

Stage 3 adds bitemporal interpretation without rewriting original payments.

Temporal model:

- `created_at` records when money originally moved.
- Every payment has immutable revisions with separate `effective_at` and `recorded_at`.
- `known_at` chooses what information was known; `as_of` chooses the effective-time view.
- Historical balance calculation includes events at the `as_of` instant.
- Corrections move only the delta between the same parties and append a revision; they
  never alter the original receipt or activity-feed item.
- Current affordability and historical nonnegative total/available constraints both
  apply. A correction that violates any historical boundary is rejected atomically.

Read surface:

- `GET /me` gains historical queries.
- `GET /statement` reports caller-only movements, window opening/closing balances,
  deltas, balances after entries, and selected revision metadata.
- Statement ordering is selected effective time then payment ID.
- Snapshot tokens freeze the selected revisions, default time, entries, and balances so
  pagination cannot drift during later writes or corrections.
- Snapshot tokens are user-specific, survive until reset, and need not survive a
  container restart.

Compatibility and concurrency:

- Payment corrections add the eighth idempotent write path.
- Optimistic revision checks ensure two corrections using one expected revision cannot
  both succeed.
- Settlement members and captured payments remain immutable to single-payment
  corrections.
- Historical holds incorporate creation, partial capture, final capture, void, and expiry
  at their event times.
- Stage 3 imports exports from the same team's Stage 1 or Stage 2 service.

### Stage 4 — refunds and atomic correction batches

Stage 4 adds reverse payments and operator-wide correction transactions.

Refunds:

- Only the original receiver refunds a direct payment, request payment, settlement
  payment, or capture.
- A refund is a new linked payment in the opposite direction, funded from the receiver's
  available balance. It does not rewrite the target receipt or reopen a request/hold.
- Cumulative refunds cannot exceed the target's current corrected amount.
- Refund payments cannot themselves be refunded or corrected.
- Refunds add the ninth idempotent write path.

Correction batches:

- An operator may atomically append 1–32 distinct payment revisions.
- Correcting one settlement member requires every member of that settlement in the same
  batch, with a common effective instant.
- Validation follows specified precedence: item errors, settlement completeness, current
  available funds, then historical total/available funds.
- Affordability is evaluated from the combined batch effect.
- Accepted revisions share one strictly increasing recorded time and batch identifier;
  rejected batches change nothing, including idempotency state.
- Conflicting concurrent batches sharing an expected revision cannot both succeed.
- Correction batches are the tenth idempotent write path.
- Stage 4 imports exports from Stages 1–3 and retains settlement membership, corrections,
  and statement snapshots.

## Cross-stage data model requirements

The architecture eventually needs these durable logical records, even if the physical
schema evolves between stage folders:

- Service configuration: currency, minor-unit precision, authorization lifetime.
- Users: stable identity, immutable handle, password hash, token identities, and wallet
  total.
- Payments: stable receipt, parties, original amount/note/visibility/time, request link,
  authorization link, settlement link, and optional refund target.
- Requests and splits: stable state, parties, calculated shares, generated requests, and
  linked payment when paid.
- Settlements: operator permission, member ordering, common commit time, and membership.
- Idempotency records: caller, method, path, parsed body value, success response, and links
  to the committed mutation. Failed 4xx attempts do not claim a key.
- Authorizations: original reservation, cumulative captures, remaining hold, lifecycle
  status, expiry, closure time, and ordered capture payments.
- Payment revisions: revision number, corrected amount, effective time, recorded time,
  reason, and optional correction-batch link.
- Statement snapshots: owning user, frozen query/window, selected revisions, balances,
  entries, and reset generation.
- Refund links and correction batches.

The model must allow an atomic snapshot for export and an atomic replacement for import.
Later-stage services must migrate earlier exports without replaying movements against
already-final balances.

## API evolution constraints

- Stage 1 defines shared parsing, authentication, error, pagination, timestamp, and
  idempotency conventions. Later endpoints inherit them unless explicitly overridden.
- Added response fields must not break earlier clients. Original idempotent responses are
  immutable even after resources change.
- UI routes that overlap API routes must negotiate HTML only for `Accept: text/html`.
- Public activity visibility never grants statement or revision-history access.
- Later historical and correction APIs must not change the semantics of ordinary current
  reads when their temporal parameters are omitted.
- Unknown body fields and query parameters remain ignored, while known malformed or
  out-of-range values follow the exact error rules.

## Concurrency and transaction boundaries

Required atomic units include:

- Reset and import state replacement.
- Direct/request payment debit-credit plus request transition and idempotency result.
- Split creation plus every generated request and idempotency result.
- Settlement validation, all transfers, all receipts, and idempotency result.
- Authorization reservation; each capture; void; and expiry-visible state transition.
- Correction delta movement, revision append, historical validation, and idempotency
  result.
- Refund movement, link creation, limit validation, and idempotency result.
- Correction-batch validation, every delta, every revision, and idempotency result.

Reads must not observe partial states. The service must sustain up to 50 in-flight
requests without overdraft, lost updates, duplicate effects, or 5xx responses.

## Runtime and offline constraints

- Each stage is a standalone folder with source, `Dockerfile`, and `RUN.md`.
- Listen on `0.0.0.0`, use `PORT`, and default to `8080`.
- `/health` must return `200 {"status":"ok"}` within 60 seconds.
- Runtime limits are 2 vCPU, 2 GiB memory, and 5 seconds per ordinary request; reset,
  export, and import have 10-second limits where specified.
- Docker builds may use outbound network. Running containers have no outbound network.
- All runtime code, fonts, scripts, styles, dependencies, initialization, and seed support
  must be inside one image. The harness ignores Compose for startup.
- Runtime disk is ephemeral. Cross-stage upgrade tests use export/import rather than
  persistent container volumes.

## Harness behavior

- `python -m harness run --track pocketful --repo <repo> --stage N` builds `stage-N/`
  and runs suites 1 through N against it.
- When a later surface exists, the harness also probes the next suite for overshoot. A
  folder that satisfies the next stage is filed at the wrong stage and claims nothing.
- `--mode isolated` starts the service and runner on an internal Docker network with no
  outbound access and enforces 2 vCPU and 2 GiB. Host mode exposes a local port and does
  not prove offline operation.
- The service must become healthy within 60 seconds. Each suite has an outer 900-second
  harness timeout.
- Every run requires a new output directory and preserves `report.json`, per-stage logs,
  and count files. Existing output directories are refused.
- Shipped Pocketful suites are partial: approximately 79%, 35%, 9%, and 16% of the four
  judged suites. A green shipped run is directional evidence, not proof of conformance.
- `claimed stage: N` is the relevant folder result; `highest contiguous stage` describes
  suites passing against that folder. The submission's achieved stage chain stops at the
  first folder that does not claim its own stage.
- `python -m harness check <repo> --track pocketful` checks layout, mandate headers and
  genericity, room-log seat/mention gates, and credential shapes. It does not build the
  service; isolated `harness run` covers container execution.
- Skips, empty suites, missing browsers, startup errors, and incomplete count files cannot
  produce a passing stage.

## Submission and collaboration evidence

Minimum repository evidence:

- `README.md` and `FACTORY.md`.
- At least three generic mandate files named after actual BAND seats. Each starts with
  the exact BAND harness and model identifiers.
- A complete, unchanged full-room export at `room.json`, reviewed for secrets before
  publishing.
- `stage-1/` at minimum; each included stage contains a complete standalone service,
  `Dockerfile`, and literal `RUN.md` instructions.
- No nested `.git` directories, submodules, symlinks, credentials, or runtime dependence
  on files outside the submitted repository.
- Git history preserving seat contributions, review findings, repairs, and stage
  progression without squashing or rewriting published collaboration evidence.

Room evidence must show at least three configured seat identities and a reciprocal
`@handle` exchange between at least two of the team's own seats. Work should be materially
distributed. A genuine rejection is useful only when it changes the work; manufactured
conflict is not required.

The final video must show the BAND room, a seat handoff, and the generated result. The
public GitHub repository, presentation, and video are all submission requirements.

## Phase boundaries established by this review

Phase 0 authorizes understanding only. It does not authorize:

- selecting a language, database, framework, locking strategy, or deployment architecture;
- implementing any endpoint or UI;
- copying the toy scaffold into the graded repository;
- installing the harness, Docker dependencies, or Playwright;
- creating Pocketful-specific mandate content;
- reading partial tests as a substitute for the specifications.

Those decisions and environment changes belong to later phases in the implementation plan.

## Open items requiring authoritative clarification

- Public kick-off Q&A or Discord rulings are not present in the pinned repository. Before
  production execution, any published Pocketful clarification must be captured verbatim
  with its source and applied consistently.
- If a specification sentence yields materially different observable behaviors, the team
  must ask through the official BAND Discord. It must not silently invent a rule.
- Runtime architecture remains deliberately undecided until the factory and environment
  phases establish checkable acceptance criteria and constraints.

## Phase 0 completion check

- All four published Pocketful stage specifications reviewed: yes.
- Cross-stage behavior and data evolution mapped: yes.
- Docker/offline/resource limits identified: yes.
- Harness execution and evidence semantics identified: yes.
- Submission gates and room/Git evidence identified: yes.
- Factory versus product responsibilities distinguished: yes.
- Application implementation started: no.
