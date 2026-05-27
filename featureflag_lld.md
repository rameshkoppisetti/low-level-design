# Low Level Design: Feature Flag System

## 1. Requirements

### Functional Requirements

- Create, update, enable, disable, and delete feature flags.
- Support boolean flags.
- Support multivariate flags such as string, number, JSON, or weighted variants.
- Evaluate a flag for a given user/context.
- Support user targeting rules.
- Support percentage rollouts.
- Support default fallback value when no rule matches.
- Cache flag definitions for low-latency evaluation.
- Maintain consistency when flags are updated.
- Audit changes to flags.

### Non-Functional Requirements

- Low latency flag evaluation, ideally in-memory or local SDK cache.
- High availability for flag reads.
- Stronger consistency for admin updates, eventual consistency for SDK caches.
- Deterministic percentage rollout for the same user.
- Safe fallback behavior when the flag service is unavailable.
- Extensible targeting conditions and variant types.

### Out of Scope

- Full experimentation analytics.
- Billing and organization management.
- Real-time metrics dashboard.
- Complex segment builder UI.
- Cross-region conflict resolution.

### Edge Cases

- Flag does not exist.
- Flag is disabled.
- User context is missing required attributes.
- Percentage rollout should be stable across calls.
- Percentage rollout should redistribute only when rollout config changes.
- Variant weights do not add up to 100.
- Cached flag is stale after admin update.
- Service unavailable during evaluation.
- Conflicting targeting rules.

## 2. APIs / Entry Points

### REST APIs

```text
POST   /flags
GET    /flags/{flagKey}
PUT    /flags/{flagKey}
PATCH  /flags/{flagKey}/enable
PATCH  /flags/{flagKey}/disable
DELETE /flags/{flagKey}

POST   /flags/{flagKey}/evaluate
POST   /evaluate

GET    /flags
GET    /flags/{flagKey}/audit
```

### Internal APIs / Events

```text
flag.updated
flag.deleted
flag.enabled
flag.disabled
```

These events are consumed by SDK caches, edge caches, or application instances to invalidate or refresh local flag definitions.

### Request DTOs

```text
CreateFlagRequest
- key
- name
- type
- enabled
- defaultValue
- variants
- rules
- rollout

EvaluateFlagRequest
- flagKey
- userId
- attributes

UserContext
- userId
- country
- email
- appVersion
- device
- customAttributes
```

### Response DTOs

```text
EvaluateFlagResponse
- flagKey
- value
- variantKey
- reason
- ruleId

FlagResponse
- key
- name
- type
- enabled
- defaultValue
- variants
- rules
- rollout
- version
- updatedAt
```

## 3. Entities & Relationships

### Core Entities

- `FeatureFlag`
  - Represents a feature flag definition.
  - Contains key, type, status, default value, variants, rules, rollout config, and version.

- `Variant`
  - Represents one possible value for a multivariate flag.
  - Example: `control`, `treatment_a`, `treatment_b`.

- `TargetingRule`
  - Defines conditions that must match a user context.
  - Returns a fixed value or a variant rollout.

- `Condition`
  - A single predicate such as `country IN ["US", "IN"]`.

- `Rollout`
  - Defines percentage-based rollout.
  - Can be boolean rollout or weighted multivariate rollout.

- `UserContext`
  - Request-time data used for evaluation.

- `AuditLog`
  - Tracks admin changes to flags.

### Enums

```text
FlagType
- BOOLEAN
- MULTIVARIATE

FlagStatus
- ENABLED
- DISABLED

Operator
- EQUALS
- NOT_EQUALS
- IN
- NOT_IN
- GREATER_THAN
- LESS_THAN
- CONTAINS

EvaluationReason
- FLAG_DISABLED
- TARGET_MATCH
- ROLLOUT_MATCH
- DEFAULT_VALUE
- ERROR_FALLBACK
```

### Relationships

```text
FeatureFlag 1 -> N Variant
FeatureFlag 1 -> N TargetingRule
TargetingRule 1 -> N Condition
FeatureFlag 1 -> 1 Rollout
FeatureFlag 1 -> N AuditLog
```

## 4. Class Design

### Controllers

```text
FeatureFlagController
- create_flag(request)
- update_flag(flag_key, request)
- enable_flag(flag_key)
- disable_flag(flag_key)
- get_flag(flag_key)
- list_flags()

EvaluationController
- evaluate(flag_key, user_context)
- bulk_evaluate(user_context)
```

### Services

```text
FeatureFlagService
- create_flag(request)
- update_flag(flag_key, request)
- enable_flag(flag_key)
- disable_flag(flag_key)
- get_flag(flag_key)

FlagEvaluationService
- evaluate(flag_key, user_context)
- evaluate_all(user_context)

AuditService
- record_change(flag_key, actor, old_value, new_value)

CacheInvalidationService
- publish_flag_updated(flag_key, version)
- handle_flag_updated(event)
```

### Interfaces

```text
FlagRepository
- save(flag)
- get_by_key(flag_key)
- list()
- delete(flag_key)

FlagCache
- get(flag_key)
- put(flag_key, flag)
- invalidate(flag_key)

RuleEvaluator
- matches(rule, user_context)

RolloutEvaluator
- evaluate(flag, user_context)
```

### Handlers / Strategies

```text
ConditionEvaluator
- EqualsEvaluator
- InEvaluator
- GreaterThanEvaluator
- ContainsEvaluator

RolloutStrategy
- BooleanPercentageRolloutStrategy
- WeightedVariantRolloutStrategy
```

### Factory Classes

```text
ConditionEvaluatorFactory
- get(operator)

RolloutStrategyFactory
- get(flag_type)
```

### Repositories

```text
FeatureFlagRepository
AuditLogRepository
```

### Workers / Consumers

```text
FlagUpdateConsumer
- consumes flag.updated events
- invalidates local/edge cache

CacheRefreshWorker
- periodically refreshes hot flags
```

## 5. DB Schema

### feature_flags

```text
id
flag_key
name
flag_type
enabled
default_value_json
rollout_config_json
version
created_at
updated_at
created_by
updated_by
```

### flag_variants

```text
id
flag_id
variant_key
value_json
weight
created_at
updated_at
```

### targeting_rules

```text
id
flag_id
rule_order
name
return_value_json
rollout_config_json
enabled
created_at
updated_at
```

### rule_conditions

```text
id
rule_id
attribute_name
operator
expected_value_json
created_at
updated_at
```

### audit_logs

```text
id
flag_id
actor_id
action
old_value_json
new_value_json
created_at
```

### Indexes

```text
feature_flags(flag_key) UNIQUE
feature_flags(enabled)
flag_variants(flag_id)
targeting_rules(flag_id, rule_order)
rule_conditions(rule_id)
audit_logs(flag_id, created_at)
```

## 6. Core Flow / Pseudocode

### Happy Path

```text
Application asks SDK/service to evaluate flag
EvaluationService checks local cache
If cache miss:
  Load flag from repository
  Store flag in cache

If flag missing:
  Return fallback

If flag disabled:
  Return default value

For each targeting rule in priority order:
  If all conditions match user context:
    Return rule value or rule rollout result

If global rollout exists:
  Return rollout result

Return default value
```

### Boolean Flag Evaluation

```text
if not flag.enabled:
  return flag.default_value

for rule in flag.rules:
  if rule.matches(user_context):
    return rule.return_value

if flag.rollout:
  bucket = hash(flag.key + user_context.user_id) % 100
  if bucket < flag.rollout.percentage:
    return True

return flag.default_value
```

### Multivariate Flag Evaluation

```text
bucket = hash(flag.key + user_context.user_id) % 100
current = 0

for variant in weighted_variants:
  current += variant.weight
  if bucket < current:
    return variant.value

return flag.default_value
```

### Failure Cases

```text
Flag not found:
  Return configured fallback/default

Cache unavailable:
  Read from DB if possible
  Otherwise return safe fallback

DB unavailable:
  Return stale cached value if allowed
  Otherwise return safe fallback

Invalid rollout weights:
  Reject flag update

Invalid targeting rule:
  Reject flag update
```

### Retry Handling

```text
Admin write fails:
  Retry request safely using idempotency key

Cache invalidation event fails:
  Consumer retries
  After max retry, move event to DLQ

SDK refresh fails:
  Continue using last known good config until TTL expires
```

### Idempotency / Concurrency

- Admin writes should use optimistic locking with `version`.
- Update API should reject stale updates:

```text
UPDATE feature_flags
SET ..., version = version + 1
WHERE flag_key = ? AND version = ?
```

- Evaluation is read-only and safe to retry.
- Percentage rollout uses deterministic hashing:

```text
bucket = stable_hash(flag_key + ":" + user_id) % 100
```

The same user gets the same result for the same flag config.

### Caching and Consistency

```text
Read path:
  SDK/local cache -> distributed cache -> DB

Write path:
  Admin updates DB
  Version increments
  Publish flag.updated event
  Consumers invalidate or refresh cache
```

Consistency model:

- Admin writes are strongly consistent in DB.
- Evaluation is eventually consistent through cache invalidation.
- SDKs may use stale-while-revalidate for availability.
- Each flag has a version so clients can detect stale config.

## 7. Extensibility

### Design Patterns

- Strategy Pattern for rollout evaluation.
- Strategy Pattern for condition evaluation.
- Factory Pattern for evaluator lookup.
- Repository Pattern for persistence.
- Observer/Event Pattern for cache invalidation.
- Chain of Responsibility style for ordered targeting rules.

### Future Changes

- Add reusable user segments.
- Add organization/project/environment isolation.
- Add SDK streaming updates using SSE/WebSocket.
- Add metrics for impressions and conversions.
- Add kill-switch priority flags.
- Add prerequisite flags.
- Add experiment analysis.

## Interview Line

“For feature flag evaluation, I keep the read path extremely fast using local or distributed cache, and I make percentage rollout deterministic using a stable hash of flag key and user id. Admin updates are versioned and persisted strongly, then propagated through invalidation events, so reads are eventually consistent but safe because SDKs can fall back to last known good values.”
