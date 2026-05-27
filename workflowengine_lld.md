# Low Level Design: Workflow Engine

## 1. Requirements

### Functional Requirements

- Create/register a workflow definition.
- A workflow contains multiple tasks.
- Tasks can depend on other tasks.
- Validate that workflow dependencies form a DAG.
- Start a workflow execution.
- Execute tasks only after dependencies are completed.
- Track workflow execution status.
- Track task execution status.
- Support retry policy per task.
- Support pluggable task handlers such as HTTP, Email, DB, or Script tasks.

### Non-Functional Requirements

- Extensible for new task types.
- Reliable task execution with retry.
- Easy to debug execution state.
- Avoid duplicate task execution where possible.
- Keep orchestration logic isolated from task-specific execution logic.

### Out of Scope

- Distributed worker cluster.
- Persistent database implementation.
- Cron scheduling.
- UI for workflow visualization.
- Event sourcing and outbox publishing.
- Advanced timeout and heartbeat handling.
- Parallel thread pool execution.

### Edge Cases

- Workflow contains cyclic dependencies.
- Task depends on unknown task id.
- No handler registered for a task type.
- Task fails after max retries.
- Workflow has no tasks.
- Multiple tasks become ready at the same time.
- Dependent task should not run if parent task failed.

## 2. APIs / Entry Points

### REST APIs

```text
POST /workflows
POST /workflows/{workflowId}/executions
GET  /executions/{executionId}
GET  /executions/{executionId}/tasks
```

### Internal APIs

```python
engine.register_workflow(workflow_id, tasks)
engine.start(workflow_id)
engine.get_execution(execution_id)
registry.register(task_type, handler)
```

### Request DTOs

```text
CreateWorkflowRequest
- workflowId
- tasks

TaskRequest
- taskId
- taskType
- dependencies
- config
- retryPolicy

RetryPolicyRequest
- maxAttempts
- backoffSeconds
```

### Response DTOs

```text
WorkflowExecutionResponse
- executionId
- workflowId
- status
- taskStatuses

TaskExecutionResponse
- taskId
- status
- attempts
- error
```

## 3. Entities & Relationships

### Core Entities

- `WorkflowDefinition`
  - Represents a registered workflow.
  - Contains task definitions by task id.

- `TaskDefinition`
  - Represents task metadata.
  - Contains task type, dependencies, config, and retry policy.

- `WorkflowExecution`
  - Runtime instance of a workflow.
  - Contains execution id, status, and task executions.

- `TaskExecution`
  - Runtime state of a task.
  - Tracks status, attempts, and error.

- `RetryPolicy`
  - Defines max attempts and backoff seconds.

### Enums

```text
WorkflowStatus
- PENDING
- RUNNING
- COMPLETED
- FAILED

TaskStatus
- PENDING
- RUNNING
- SUCCESS
- FAILED
```

### Relationships

```text
WorkflowDefinition 1 -> N TaskDefinition
WorkflowExecution 1 -> 1 WorkflowDefinition
WorkflowExecution 1 -> N TaskExecution
TaskExecution N -> 1 TaskDefinition
TaskDefinition N -> N TaskDefinition through dependencies
```

## 4. Class Design

### Controllers

```text
WorkflowController
- create_workflow(request)
- start_workflow(workflow_id)
- get_execution(execution_id)
```

For the simplified in-memory version, controller code is omitted and `WorkflowEngine` is used directly.

### Services

```text
WorkflowEngine
- register_workflow(workflow_id, tasks)
- start(workflow_id)
- get_execution(execution_id)
- _validate_workflow(tasks)
- _run(execution)
- _get_ready_tasks(execution)
- _execute_task(execution, task_execution)
- _update_workflow_status(execution)
```

`WorkflowEngine` is the central orchestrator. It validates DAGs, creates executions, finds ready tasks, executes tasks, applies retry policy, and marks workflow status.

### Interfaces

```text
TaskHandler
- execute(task_definition)
```

### Handlers / Strategies

```text
HttpTaskHandler
EmailTaskHandler
```

Each task type has its own handler. The workflow engine does not know how HTTP or Email execution works.

### Factory / Registry Classes

```text
TaskHandlerRegistry
- register(task_type, handler)
- get(task_type)
```

This avoids `if task_type == ...` branching inside the engine.

### Repositories

For this simplified LLD, repositories are in-memory dictionaries inside `WorkflowEngine`:

```text
workflows: workflowId -> WorkflowDefinition
executions: executionId -> WorkflowExecution
```

In production, these can become:

```text
WorkflowRepository
WorkflowExecutionRepository
TaskExecutionRepository
```

### Workers / Consumers

For this simplified version, execution is synchronous inside `WorkflowEngine.start()`.

Future production design can add:

```text
SchedulerWorker
TaskWorker
RetryWorker
```

## 5. DB Schema

For the simplified code, storage is in-memory. A production schema can be:

### workflows

```text
id
workflow_id
name
created_at
updated_at
```

### workflow_tasks

```text
id
workflow_id
task_id
task_type
config_json
retry_max_attempts
retry_backoff_seconds
```

### task_dependencies

```text
id
workflow_id
task_id
depends_on_task_id
```

### workflow_executions

```text
id
execution_id
workflow_id
status
created_at
updated_at
```

### task_executions

```text
id
execution_id
task_id
status
attempts
error
created_at
updated_at
```

### Indexes

```text
workflow_tasks(workflow_id)
task_dependencies(workflow_id, task_id)
workflow_executions(workflow_id, status)
task_executions(execution_id, status)
```

## 6. Core Flow / Pseudocode

### Happy Path

```text
Client registers workflow
Engine validates DAG
Engine stores WorkflowDefinition

Client starts workflow
Engine creates WorkflowExecution
Engine creates TaskExecution for each task

Loop:
  Find PENDING tasks whose dependencies are SUCCESS
  Execute ready tasks using TaskHandlerRegistry
  Mark task SUCCESS
  Repeat until no ready task remains

If all tasks SUCCESS:
  Mark workflow COMPLETED
```

### Failure Cases

```text
If workflow id does not exist:
  Raise error

If task dependency is invalid:
  Reject workflow registration

If dependency cycle exists:
  Reject workflow registration

If no handler exists:
  Mark task FAILED
  Mark workflow FAILED

If task fails after retries:
  Mark task FAILED
  Mark workflow FAILED
```

### Retry Handling

```text
attempts = 0

while attempts < max_attempts:
  try:
    attempts += 1
    handler.execute(task)
    mark SUCCESS
    return
  except Exception:
    sleep(backoff_seconds)

mark FAILED
```

### Idempotency / Concurrency

- Each workflow execution gets a unique `execution_id`.
- Each task has one `TaskExecution` per workflow execution.
- A task only runs when status is `PENDING`.
- In a distributed version, task claiming should use DB row locks or compare-and-swap status update:

```text
UPDATE task_executions
SET status = RUNNING
WHERE id = ? AND status = PENDING
```

## 7. Extensibility

### Design Patterns

- Strategy Pattern: `TaskHandler` implementations execute different task types.
- Registry Pattern: `TaskHandlerRegistry` maps task type to handler.
- Template Method style: workflow execution follows a fixed orchestration algorithm while handlers customize task behavior.
- Repository Pattern can be introduced later for persistence.

### Future Changes

- Add async worker pool for parallel ready tasks.
- Add persistent DB repositories.
- Add timeout and heartbeat support.
- Add cron-based scheduled workflow triggers.
- Add event publishing for workflow/task status changes.
- Add pause, resume, and cancel workflow.
- Add compensation tasks for saga workflows.

## Interview Line

“I keep `WorkflowEngine` responsible for orchestration: DAG validation, dependency resolution, execution state, and retries. Task-specific logic is delegated to `TaskHandler` implementations, so adding a new task type does not require changing the engine. For a production distributed version, I would move in-memory maps into repositories and add worker-based task claiming with idempotent status transitions.”
