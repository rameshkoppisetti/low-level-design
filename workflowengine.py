from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from threading import Lock
from typing import Dict, List, Optional, Any
import time
import uuid


# =========================
# ENUMS
# =========================

class WorkflowStatus(Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class TaskStatus(Enum):
    PENDING = "PENDING"
    READY = "READY"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    RETRY_SCHEDULED = "RETRY_SCHEDULED"
    TIMED_OUT = "TIMED_OUT"


class OutboxStatus(Enum):
    PENDING = "PENDING"
    PUBLISHED = "PUBLISHED"


# =========================
# MODELS
# =========================

@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int
    backoff_seconds: int


@dataclass(frozen=True)
class TaskDefinition:
    task_id: str
    task_type: str
    dependencies: List[str]
    config: Dict[str, Any]
    retry_policy: RetryPolicy
    timeout_seconds: int


@dataclass
class WorkflowVersion:
    workflow_id: str
    version: int
    tasks: Dict[str, TaskDefinition]


@dataclass
class WorkflowExecution:
    execution_id: str
    workflow_id: str
    version: int
    status: WorkflowStatus = WorkflowStatus.PENDING
    version_number: int = 0
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    lock: Lock = field(default_factory=Lock, repr=False)


@dataclass
class TaskExecution:
    task_execution_id: str
    execution_id: str
    task_id: str
    status: TaskStatus = TaskStatus.PENDING
    attempt: int = 0
    next_retry_at: Optional[float] = None
    last_heartbeat_at: Optional[float] = None
    worker_id: Optional[str] = None
    error: Optional[str] = None
    lock: Lock = field(default_factory=Lock, repr=False)


@dataclass(frozen=True)
class ExecutionEvent:
    event_id: str
    execution_id: str
    event_type: str
    payload: Dict[str, Any]
    created_at: float = field(default_factory=time.time)


@dataclass
class OutboxEvent:
    event_id: str
    aggregate_id: str
    event_type: str
    payload: Dict[str, Any]
    status: OutboxStatus = OutboxStatus.PENDING


# =========================
# HANDLER INTERFACE
# =========================

class TaskHandler(ABC):

    @abstractmethod
    def execute(self, task: TaskDefinition, execution: TaskExecution) -> None:
        pass


class HttpTaskHandler(TaskHandler):
    def execute(self, task: TaskDefinition, execution: TaskExecution) -> None:
        print(f"Executing HTTP task: {task.task_id}")


class EmailTaskHandler(TaskHandler):
    def execute(self, task: TaskDefinition, execution: TaskExecution) -> None:
        print(f"Executing EMAIL task: {task.task_id}")


class TaskHandlerRegistry:

    def __init__(self):
        self.handlers: Dict[str, TaskHandler] = {}

    def register(self, task_type: str, handler: TaskHandler) -> None:
        self.handlers[task_type] = handler

    def get(self, task_type: str) -> TaskHandler:
        if task_type not in self.handlers:
            raise ValueError(f"No handler registered for {task_type}")
        return self.handlers[task_type]


# =========================
# REPOSITORIES
# =========================

class WorkflowDefinitionRepository:

    def __init__(self):
        self.versions: Dict[tuple[str, int], WorkflowVersion] = {}

    def save_version(self, version: WorkflowVersion) -> None:
        self.versions[(version.workflow_id, version.version)] = version

    def get_version(self, workflow_id: str, version: int) -> WorkflowVersion:
        return self.versions[(workflow_id, version)]


class WorkflowExecutionRepository:

    def __init__(self):
        self.executions: Dict[str, WorkflowExecution] = {}

    def save(self, execution: WorkflowExecution) -> None:
        self.executions[execution.execution_id] = execution

    def get(self, execution_id: str) -> WorkflowExecution:
        return self.executions[execution_id]

    def scan_recoverable(self) -> List[WorkflowExecution]:
        return [
            execution
            for execution in self.executions.values()
            if execution.status in {WorkflowStatus.PENDING, WorkflowStatus.RUNNING}
        ]


class TaskExecutionRepository:

    def __init__(self):
        self.tasks: Dict[str, TaskExecution] = {}
        self.by_execution: Dict[str, List[str]] = {}

    def save(self, task_execution: TaskExecution) -> None:
        self.tasks[task_execution.task_execution_id] = task_execution
        self.by_execution.setdefault(
            task_execution.execution_id, []
        ).append(task_execution.task_execution_id)

    def get_tasks_for_execution(self, execution_id: str) -> List[TaskExecution]:
        return [
            self.tasks[task_execution_id]
            for task_execution_id in self.by_execution.get(execution_id, [])
        ]


class EventStore:

    def __init__(self):
        self.events_by_execution: Dict[str, List[ExecutionEvent]] = {}

    def append(self, event: ExecutionEvent) -> None:
        self.events_by_execution.setdefault(event.execution_id, []).append(event)

    def get_events(self, execution_id: str) -> List[ExecutionEvent]:
        return self.events_by_execution.get(execution_id, [])


class OutboxRepository:

    def __init__(self):
        self.events: Dict[str, OutboxEvent] = {}

    def save(self, event: OutboxEvent) -> None:
        self.events[event.event_id] = event

    def pending_events(self) -> List[OutboxEvent]:
        return [
            event for event in self.events.values()
            if event.status == OutboxStatus.PENDING
        ]


# =========================
# SERVICES
# =========================

class WorkflowService:

    def __init__(self, workflow_repo: WorkflowDefinitionRepository):
        self.workflow_repo = workflow_repo

    def create_workflow_version(
        self,
        workflow_id: str,
        version: int,
        tasks: List[TaskDefinition],
    ) -> None:
        task_map = {task.task_id: task for task in tasks}
        self._validate_dag(task_map)

        workflow_version = WorkflowVersion(
            workflow_id=workflow_id,
            version=version,
            tasks=task_map,
        )

        self.workflow_repo.save_version(workflow_version)

    def _validate_dag(self, tasks: Dict[str, TaskDefinition]) -> None:
        visited = set()
        visiting = set()

        def dfs(task_id: str):
            if task_id in visiting:
                raise ValueError("Cycle detected in workflow")
            if task_id in visited:
                return

            visiting.add(task_id)

            for dep in tasks[task_id].dependencies:
                if dep not in tasks:
                    raise ValueError(f"Invalid dependency {dep}")
                dfs(dep)

            visiting.remove(task_id)
            visited.add(task_id)

        for task_id in tasks:
            dfs(task_id)


class WorkflowExecutionService:

    def __init__(
        self,
        workflow_repo: WorkflowDefinitionRepository,
        execution_repo: WorkflowExecutionRepository,
        task_repo: TaskExecutionRepository,
        event_store: EventStore,
        outbox_repo: OutboxRepository,
    ):
        self.workflow_repo = workflow_repo
        self.execution_repo = execution_repo
        self.task_repo = task_repo
        self.event_store = event_store
        self.outbox_repo = outbox_repo

    def trigger_workflow(self, workflow_id: str, version: int) -> str:
        workflow_version = self.workflow_repo.get_version(workflow_id, version)

        execution_id = str(uuid.uuid4())

        execution = WorkflowExecution(
            execution_id=execution_id,
            workflow_id=workflow_id,
            version=version,
            status=WorkflowStatus.RUNNING,
        )

        self.execution_repo.save(execution)

        for task_id in workflow_version.tasks:
            task_execution = TaskExecution(
                task_execution_id=str(uuid.uuid4()),
                execution_id=execution_id,
                task_id=task_id,
            )
            self.task_repo.save(task_execution)

        self._append_event(execution_id, "WORKFLOW_STARTED", {})

        return execution_id

    def mark_task_success(self, execution: WorkflowExecution, task: TaskExecution) -> None:
        with execution.lock:
            with task.lock:
                if task.status == TaskStatus.SUCCESS:
                    return

                task.status = TaskStatus.SUCCESS
                execution.version_number += 1
                execution.updated_at = time.time()

                self._append_event(
                    execution.execution_id,
                    "TASK_COMPLETED",
                    {"task_id": task.task_id},
                )

    def _append_event(
        self,
        execution_id: str,
        event_type: str,
        payload: Dict[str, Any],
    ) -> None:
        event = ExecutionEvent(
            event_id=str(uuid.uuid4()),
            execution_id=execution_id,
            event_type=event_type,
            payload=payload,
        )

        self.event_store.append(event)

        outbox_event = OutboxEvent(
            event_id=str(uuid.uuid4()),
            aggregate_id=execution_id,
            event_type=event_type,
            payload=payload,
        )

        self.outbox_repo.save(outbox_event)


class SchedulerService:

    def __init__(
        self,
        workflow_repo: WorkflowDefinitionRepository,
        execution_repo: WorkflowExecutionRepository,
        task_repo: TaskExecutionRepository,
    ):
        self.workflow_repo = workflow_repo
        self.execution_repo = execution_repo
        self.task_repo = task_repo

    def get_ready_tasks(self, execution_id: str) -> List[TaskExecution]:
        execution = self.execution_repo.get(execution_id)
        workflow_version = self.workflow_repo.get_version(
            execution.workflow_id,
            execution.version,
        )

        task_executions = self.task_repo.get_tasks_for_execution(execution_id)
        task_by_id = {task.task_id: task for task in task_executions}

        ready = []

        for task_execution in task_executions:
            if task_execution.status not in {
                TaskStatus.PENDING,
                TaskStatus.RETRY_SCHEDULED,
            }:
                continue

            if (
                task_execution.status == TaskStatus.RETRY_SCHEDULED
                and task_execution.next_retry_at
                and time.time() < task_execution.next_retry_at
            ):
                continue

            task_def = workflow_version.tasks[task_execution.task_id]

            deps_completed = all(
                task_by_id[dep].status == TaskStatus.SUCCESS
                for dep in task_def.dependencies
            )

            if deps_completed:
                task_execution.status = TaskStatus.READY
                ready.append(task_execution)

        return ready


class WorkerService:

    def __init__(
        self,
        workflow_repo: WorkflowDefinitionRepository,
        execution_repo: WorkflowExecutionRepository,
        execution_service: WorkflowExecutionService,
        handler_registry: TaskHandlerRegistry,
    ):
        self.workflow_repo = workflow_repo
        self.execution_repo = execution_repo
        self.execution_service = execution_service
        self.handler_registry = handler_registry

    def execute_task(self, task_execution: TaskExecution) -> None:
        execution = self.execution_repo.get(task_execution.execution_id)

        workflow_version = self.workflow_repo.get_version(
            execution.workflow_id,
            execution.version,
        )

        task_def = workflow_version.tasks[task_execution.task_id]

        with task_execution.lock:
            if task_execution.status not in {TaskStatus.READY, TaskStatus.RETRY_SCHEDULED}:
                return

            task_execution.status = TaskStatus.RUNNING
            task_execution.attempt += 1
            task_execution.last_heartbeat_at = time.time()

        try:
            handler = self.handler_registry.get(task_def.task_type)
            handler.execute(task_def, task_execution)

            self.execution_service.mark_task_success(execution, task_execution)

        except Exception as ex:
            with task_execution.lock:
                task_execution.error = str(ex)

                if task_execution.attempt < task_def.retry_policy.max_attempts:
                    task_execution.status = TaskStatus.RETRY_SCHEDULED
                    task_execution.next_retry_at = (
                        time.time() + task_def.retry_policy.backoff_seconds
                    )
                else:
                    task_execution.status = TaskStatus.FAILED


# =========================
# DEMO
# =========================

def main():
    workflow_repo = WorkflowDefinitionRepository()
    execution_repo = WorkflowExecutionRepository()
    task_repo = TaskExecutionRepository()
    event_store = EventStore()
    outbox_repo = OutboxRepository()

    registry = TaskHandlerRegistry()
    registry.register("HTTP", HttpTaskHandler())
    registry.register("EMAIL", EmailTaskHandler())

    workflow_service = WorkflowService(workflow_repo)

    execution_service = WorkflowExecutionService(
        workflow_repo,
        execution_repo,
        task_repo,
        event_store,
        outbox_repo,
    )

    scheduler = SchedulerService(
        workflow_repo,
        execution_repo,
        task_repo,
    )

    worker = WorkerService(
        workflow_repo,
        execution_repo,
        execution_service,
        registry,
    )

    fetch = TaskDefinition(
        task_id="fetch",
        task_type="HTTP",
        dependencies=[],
        config={},
        retry_policy=RetryPolicy(max_attempts=3, backoff_seconds=2),
        timeout_seconds=30,
    )

    notify = TaskDefinition(
        task_id="notify",
        task_type="EMAIL",
        dependencies=["fetch"],
        config={},
        retry_policy=RetryPolicy(max_attempts=2, backoff_seconds=2),
        timeout_seconds=30,
    )

    workflow_service.create_workflow_version(
        workflow_id="daily_etl",
        version=1,
        tasks=[fetch, notify],
    )

    execution_id = execution_service.trigger_workflow("daily_etl", 1)

    while True:
        ready_tasks = scheduler.get_ready_tasks(execution_id)

        if not ready_tasks:
            break

        for task in ready_tasks:
            worker.execute_task(task)

    events = event_store.get_events(execution_id)

    print("Execution Events:")
    for event in events:
        print(event.event_type, event.payload)

    print("Outbox Events:")
    for event in outbox_repo.pending_events():
        print(event.event_type, event.status.value)


if __name__ == "__main__":
    main()