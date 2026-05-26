Workflow Orchestration LLD — Correct Interview Version
0. Opening line
Let me clarify requirements, define workflow/task models, state transitions, scheduler, workers, queues, retry handling, persistence, and then discuss recovery, idempotency, and scaling.
1. Correct Problem Statement

Design a Workflow Orchestration Engine similar to Temporal / Airflow / Cadence / Conductor.

The system should allow users to define workflows as a DAG or state machine, execute tasks reliably, support retries/timeouts/failures, persist execution state, and recover after crashes. In production, workflow engines must not rely only on memory; they must persist request state, current stage, workflow version, and execution history.

2. Functional Requirements
1. User can create workflow definition.
2. Workflow has multiple tasks/stages.
3. Tasks can have dependencies.
4. User can trigger workflow execution.
5. Scheduler finds ready tasks.
6. Workers execute tasks.
7. System supports retry with backoff.
8. System tracks workflow/task status.
9. System recovers after crash.
10. System avoids duplicate transitions.
11. System supports workflow versioning.
3. Non-Functional Requirements
1. Reliable execution.
2. Persistent state.
3. Idempotent task execution.
4. Ordered events per workflow/request.
5. Horizontally scalable workers.
6. Retry + DLQ support.
7. Backpressure support.
8. Auditability through execution history.

Strong line:

The hard part is not just executing tasks. The hard part is distributed consistency, recovery, retries, idempotency, ordering, and avoiding duplicate transitions.

That matches the uploaded notes: workflow orchestration’s hardest problems are distributed consistency and failure recovery, with idempotency, retries, ordering, outbox, replay, and compensation being key senior signals.

4. Core Entities
WorkflowDefinition
WorkflowVersion
WorkflowStage / TaskDefinition
WorkflowTransition
WorkflowExecution
TaskExecution
ExecutionEvent
RetryPolicy
Worker
TaskQueue
OutboxEvent
IdempotencyRecord
Relationships
WorkflowDefinition -> WorkflowVersion
WorkflowVersion -> TaskDefinitions
TaskDefinition -> Dependencies
WorkflowExecution -> TaskExecutions
WorkflowExecution -> ExecutionEvents
TaskExecution -> RetryPolicy
TaskQueue -> TaskExecution
Worker -> TaskHandler
5. State Models
WorkflowExecutionStatus
PENDING
RUNNING
COMPLETED
FAILED
CANCELLED
TIMED_OUT
TaskExecutionStatus
PENDING
READY
RUNNING
SUCCESS
FAILED
RETRY_SCHEDULED
TIMED_OUT
SKIPPED
6. APIs / Service Methods
createWorkflow(definition) -> workflow_id
publishWorkflowVersion(workflow_id, version_config) -> version
triggerWorkflow(workflow_id, input, idempotency_key) -> execution_id
getWorkflowStatus(execution_id)
cancelWorkflow(execution_id)

registerTaskHandler(task_type, handler)

worker.poll(queue_name)
worker.complete(task_execution_id, result)
worker.fail(task_execution_id, error)

scheduler.scanAndEnqueueReadyTasks()
7. High-Level Flow
User triggers workflow
   ↓
WorkflowExecution created with workflow_id + version
   ↓
Initial TaskExecutions created
   ↓
Scheduler scans READY tasks
   ↓
Tasks pushed to queue
   ↓
Worker polls task
   ↓
Worker heartbeats while running
   ↓
Worker completes/fails task
   ↓
State transition persisted
   ↓
Dependent tasks become READY
   ↓
Workflow completes when all tasks finish
8. Correct Architecture
Workflow API
   ↓
Workflow Service
   ↓
Workflow DB  ← source of truth
   ↓
Outbox Table
   ↓
Outbox Publisher
   ↓
Kafka / Queue
   ↓
Scheduler / Task Dispatcher
   ↓
Worker Pool
   ↓
Task Handlers

Important:

DB is source of truth.
Kafka/Queue is for async execution.
Outbox prevents lost events.
Workers are stateless and idempotent.
9. DB Schema
workflow_definition
workflow_id
name
created_at
created_by
workflow_version
workflow_id
version
status
definition_json
created_at

Important senior point:

Workflow versions must be immutable. Old executions continue on old version. New executions use latest version.

Your uploaded notes also mention this: active requests should bind to workflow_id + version, and existing versions should not be mutated; instead create v2 and let old executions continue on v1.

task_definition
task_id
workflow_id
version
task_type
config_json
retry_policy_json
timeout_seconds
task_dependency
task_id
depends_on_task_id
workflow_execution
execution_id
workflow_id
version
status
current_stage
input_json
version_number
created_at
updated_at

version_number is for optimistic locking.

task_execution
task_execution_id
execution_id
task_id
status
attempt
next_retry_at
last_heartbeat_at
worker_id
error
created_at
updated_at
execution_event
event_id
execution_id
event_type
payload_json
created_at
idempotency_record
idempotency_key
operation_type
resource_id
response_json
created_at
outbox_event
event_id
aggregate_id
event_type
payload_json
status
created_at
published_at
10. Key Design Decisions
A. Crash Recovery

Wrong:

Keep workflow state only in memory.

Correct:

Persist every workflow and task state transition.

Recovery flow:

After restart:
1. Scheduler scans PENDING / RUNNING / RETRY_SCHEDULED / TIMED_OUT tasks.
2. If task heartbeat is stale, mark it retryable.
3. Re-enqueue ready tasks.
4. Resume workflow from persisted state.

The uploaded notes explicitly call out that workflow state must be persisted externally and recovery should scan RUNNING, PENDING, and TIMED_OUT workflows, then resume/retry/re-enqueue tasks.

B. Avoid Duplicate Transitions

Use optimistic locking.

UPDATE workflow_execution
SET current_stage = 'FINANCE',
    version_number = version_number + 1,
    updated_at = now()
WHERE execution_id = ?
  AND version_number = ?
  AND current_stage = 'MANAGER';

If rows updated = 0:

Another worker already transitioned this workflow.

Also use idempotency:

approve_request(execution_id, idempotency_key)

Store processed keys.

This is one of the most important workflow questions: optimistic locking prevents duplicate transitions, while idempotency keys prevent duplicate side effects.

C. Replay / Event Sourcing

Store immutable events:

WORKFLOW_STARTED
TASK_READY
TASK_STARTED
TASK_COMPLETED
TASK_FAILED
TASK_RETRY_SCHEDULED
WORKFLOW_COMPLETED
WORKFLOW_FAILED

Replay:

state = reducer(events)

Benefits:

debugging
audit
recovery
analytics
migration validation

Temporal/Cadence-style engines heavily use replay/event history. Your uploaded notes also describe replay by storing immutable events and reconstructing state using a reducer.

D. Dynamic Workflows

Avoid hardcoding:

if manager_approved:
    go_to_finance()

Correct:

Store workflow config in DB.
Workflow engine interprets config at runtime.

Tables:

workflow_definition
workflow_stage
workflow_transition
approval_rules

This allows:

conditional branching
parallel approvals
loops
dynamic approvers
amount > 1M -> CFO approval

This is the “workflow-as-data” model from your notes.

E. Ordering

Use Kafka partition key:

execution_id / request_id

Guarantees:

All events for same workflow go to same partition.
Ordering is preserved per workflow.

Your notes call this out: partitioning by request_id ensures events like APPROVE before COMPLETE are not reordered.

F. Retry

Retry policy:

max_retries
backoff_strategy
retryable_errors

Use exponential backoff + jitter:

1s, 2s, 4s, 8s + random jitter

Queue pattern:

main-topic
retry-5s
retry-1m
DLQ

Only retry transient failures, not validation failures. This distinction is explicitly mentioned in the uploaded notes.

G. Transactional Outbox

Problem:

DB update succeeds, Kafka publish fails.

Correct solution:

Inside same DB transaction:
1. update workflow/task state
2. insert outbox event
3. commit

Async publisher:
1. reads outbox
2. publishes Kafka
3. marks event as sent

This avoids the dual-write problem and is a major senior-level workflow point.

11. Class Design
WorkflowController
WorkflowService
WorkflowExecutionService
SchedulerService
TaskDispatcher
WorkerService
TaskHandlerRegistry
RetryService
OutboxService
EventStoreService

WorkflowRepository
WorkflowExecutionRepository
TaskExecutionRepository
OutboxRepository
IdempotencyRepository

TaskHandler interface
HttpTaskHandler
EmailTaskHandler
ApprovalTaskHandler
DataProcessingTaskHandler