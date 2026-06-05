## Why

The current paper subscription flow allows any visitor to subscribe, has no self-service unsubscribe path, and uses fixed delivery/filtering behavior that may overgrow server load or send too many/low-value papers. Adding access controls, unsubscribe, and configurable delivery/query quality controls makes the service safer to operate as public exposure and subscriber count grow.

## What Changes

- Add subscription access control so only authorized users can create subscriptions, using an operator-configurable gate suitable for a small private service.
- Add a self-service unsubscribe flow that marks subscriptions inactive and prevents future delivery.
- Make daily per-subscriber push count configurable, with a default target of 10 papers.
- Make fetch/query frequency configurable for the daemon so operators can collect more papers when current volume is low.
- Add a web browsing quality filter so low-quality papers can be hidden from the list by default or by configured threshold.
- Ensure pipeline subscription loading and delivery respect inactive subscriptions and the configured delivery count.

## Capabilities

### New Capabilities
- `subscription-access-control`: Controls who may create web subscriptions and how unauthorized attempts are rejected.
- `unsubscribe-management`: Allows subscribed recipients to cancel future paper digests and records inactive status.
- `delivery-volume-control`: Configures per-user/default paper push count and daemon query frequency for paper digest delivery.

### Modified Capabilities
- `subscription-form`: Subscription form submission must satisfy access control before creating a subscription.
- `subscription-storage`: Subscription persistence must support inactive/unsubscribed subscriptions and exclude them from runtime delivery.
- `paper-browsing`: Paper list browsing must support filtering out low-quality papers by configured/default threshold.

## Impact

- Affected config models and examples: `src/paper_agent/config.py`, `config.example.yaml`.
- Affected web routes/templates: subscription form, subscribe API, new unsubscribe route/API, paper list filters.
- Affected storage: `subscriptions` status updates and query helpers; paper browsing query filters.
- Affected pipeline/scheduler: top-N delivery defaults, subscription loading, daemon trigger frequency.
- Affected tests: subscription authorization, unsubscribe behavior, delivery count/frequency config, paper browsing quality filter.
