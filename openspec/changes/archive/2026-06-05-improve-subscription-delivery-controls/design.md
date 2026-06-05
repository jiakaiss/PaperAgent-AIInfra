## Context

The project currently supports a public web subscription form, runtime conversion of subscription rows into `UserConfig`, local SQLite storage for paper score cache and delivery tracking, and a daemon that runs the pipeline on a single daily cron. Subscriptions are accepted when global email config is valid, stored with `status='active'`, and loaded at CLI/web startup. Paper delivery volume is controlled by each user's `thresholds.top_n`, whose default is currently 20, while web paper browsing reads scored papers from SQLite and sorts by score.

The requested change spans web UX, database helpers, config, pipeline delivery, scheduler behavior, and paper browsing. The main operational concern is protecting a small server from unrestricted subscriber growth while also giving recipients a way out and improving digest quality/volume controls.

## Goals / Non-Goals

**Goals:**
- Restrict web subscription creation to authorized visitors using simple operator-configured access control.
- Provide self-service unsubscribe that deactivates a subscription and excludes it from future delivery.
- Make subscription/default delivery count configurable, defaulting new subscription users to 10 papers per digest.
- Allow the daemon to run more frequently than once per day via configuration.
- Allow web browsing to hide low-quality papers using a configurable/default quality threshold.
- Preserve current config-file users and existing active subscriptions through a safe migration path.

**Non-Goals:**
- Full user accounts, passwords, sessions, OAuth, or role-based admin management.
- Per-recipient preference editing beyond unsubscribe.
- Guaranteed delivery retries or per-notifier partial failure semantics.
- Re-scoring existing cached papers or changing Claude scoring prompts.

## Decisions

### Use an invite/access-code gate for subscription creation

Add a top-level web/subscription access configuration with an `enabled` flag and one or more allowed access codes. The subscription form includes an access-code field when the gate is enabled, and `/api/subscribe` validates the submitted code before saving anything.

Rationale: this solves the immediate "not everyone can subscribe" problem without introducing accounts, sessions, password reset, or admin UI. It is easy to operate for a private newsletter: the operator shares a code with approved recipients.

Alternatives considered:
- HTTP Basic Auth for the whole web app: simple but would block public paper browsing too, not just subscription creation.
- Admin approval queue: more robust but requires extra status states, admin UI, and moderation workflow.
- Email allowlist only: useful for companies but less flexible for small groups and harder to share casually.

### Represent unsubscribe as `status='inactive'` plus timestamp metadata

Keep the existing `subscriptions` table and add optional unsubscribe metadata rather than deleting rows. Active loaders continue to read only `status='active'`; unsubscribe updates the row to `inactive` and records an unsubscribe timestamp when supported by the migration.

Rationale: preserving rows avoids duplicate historical ambiguity, enables clear duplicate handling, and prevents accidental reactivation unless explicitly supported later.

Alternatives considered:
- Delete subscription rows: simpler but loses audit/history and makes duplicate handling less informative.
- Add a separate unsubscribe table: unnecessary for current requirements.

### Use signed unsubscribe tokens derived from config secret

Digest emails include an unsubscribe link containing the recipient email and a signed token. The web route verifies the token before deactivating the subscription.

Rationale: avoids requiring login while preventing arbitrary visitors from unsubscribing someone else by only knowing their email. The secret can be configured and should default to an operator-provided value in production.

Alternatives considered:
- Plain email POST form: easier, but anyone can unsubscribe any address.
- Random per-subscription token stored in database: robust, but requires schema changes for every existing row. It remains a future enhancement if link rotation is needed.

### Centralize delivery defaults in configuration and keep per-user override

Add a configurable default delivery count for subscription-created users, defaulting to 10. Existing explicit `UserConfig.thresholds.top_n` values continue to work. `subscription_to_user_config()` sets the subscription user's `thresholds.top_n` from the configured default.

Rationale: config-file users already have per-user threshold support; subscription users need a global default without requiring each row to store thresholds.

Alternatives considered:
- Store top_n per subscription: more flexible but requires preference editing UI.
- Change `UserThresholdsConfig.top_n` default globally to 10 only: simple, but less explicit for subscription-created users and could alter existing config users that rely on implicit defaults.

### Add scheduler interval mode while retaining cron mode

Extend schedule config to support either cron-style daily execution or interval execution in minutes. The daemon creates the appropriate APScheduler trigger from config.

Rationale: operators can increase collection frequency when paper volume is low without changing code or running multiple daemons.

Alternatives considered:
- Multiple cron entries: more verbose and less ergonomic.
- Always run hourly: too opinionated for deployments that only want daily digest behavior.

### Apply web low-quality filtering in database query layer

Extend paper listing/count methods with `min_quality` and route-level default configuration. The filter is applied in SQL alongside sub-domain/search/time filters.

Rationale: the server should avoid returning hidden low-quality rows for pagination correctness and consistent counts.

Alternatives considered:
- Filter in templates/client JS: pagination totals become wrong and unnecessary rows are loaded.
- Delete low-quality rows from cache: loses data and prevents later threshold changes.

## Risks / Trade-offs

- Access codes are shared secrets and can leak → allow multiple codes, document rotation, and avoid logging submitted codes.
- Signed unsubscribe links require a stable secret → warn or fail clearly when unsubscribe links are enabled without a configured secret.
- Existing subscriptions lack unsubscribe metadata columns → perform idempotent SQLite migrations with `ALTER TABLE` checks and keep status-based behavior compatible.
- Increasing query frequency can hit arXiv rate limits or increase Claude API cost → keep existing fetch dedup/cache, expose config with conservative defaults, and document operational impact.
- Lowering delivered `top_n` from 20 to 10 may surprise some users → apply the new default to subscription-created users and allow explicit per-user overrides.
- Web min-quality filtering could hide useful niche papers → make the threshold configurable and allow disabling by setting it to `0` or `null` depending on final config shape.

## Migration Plan

1. Add new config fields with backward-compatible defaults: subscription access disabled unless configured, unsubscribe enabled when secret exists, subscription default top_n set to 10, current daily cron schedule preserved, web quality filter configurable.
2. Add idempotent database migration for unsubscribe metadata columns while preserving existing `status` values.
3. Update subscription loading to continue loading only `status='active'` rows.
4. Update web form and API to enforce access control only when enabled.
5. Update notifier formatting to include unsubscribe links for subscription email users when token config is available.
6. Rollback is safe by reverting code: existing rows remain compatible because core active/inactive `status` semantics are unchanged.

## Open Questions

- Should access control use only shared codes, or should an email allowlist also be included in the first implementation?
- Should paper browsing expose a UI toggle for low-quality papers, or only apply a configured server default initially?
- Should unsubscribe support later re-subscribe of the same email, or should inactive rows block duplicate subscription until an explicit reactivation flow is added?
