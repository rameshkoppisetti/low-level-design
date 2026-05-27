from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional
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


class TaskStatus(Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


# =========================
# MODELS
# =========================

@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 1
    backoff_seconds: int = 0


@dataclass(frozen=True)
class TaskDefinition:
    task_id: str
    task_type: str
    dependencies: List[str] = field(default_factory=list)
    config: Dict[str, Any] = field(default_factory=dict)
    retry_policy: RetryPolicy = field(default_factory=RetryPolicy)


@dataclass
class WorkflowDefinition:
    workflow_id: str
    tasks: Dict[str, TaskDefinition]
    topological_order: List[str]


@dataclass
class TaskExecution:
    task_id: str
    status: TaskStatus = TaskStatus.PENDING
    attempts: int = 0
    error: Optional[str] = None


@dataclass
class WorkflowExecution:
    execution_id: str
    workflow: WorkflowDefinition
    status: WorkflowStatus = WorkflowStatus.PENDING
    task_executions: Dict[str, TaskExecution] = field(default_factory=dict)


# =========================
# TASK HANDLERS
# =========================

class TaskHandler(ABC):

    @abstractmethod
    def execute(self, task: TaskDefinition) -> None:
        pass


class HttpTaskHandler(TaskHandler):
    def execute(self, task: TaskDefinition) -> None:
        print(f"Executing HTTP task: {task.task_id}")


class EmailTaskHandler(TaskHandler):
    def execute(self, task: TaskDefinition) -> None:
        print(f"Executing EMAIL task: {task.task_id}")


class TaskHandlerRegistry:

    def __init__(self):
        self.handlers: Dict[str, TaskHandler] = {}

    def register(self, task_type: str, handler: TaskHandler) -> None:
        self.handlers[task_type] = handler

    def get(self, task_type: str) -> TaskHandler:
        if task_type not in self.handlers:
            raise ValueError(f"No handler registered for task type: {task_type}")
        return self.handlers[task_type]


# =========================
# WORKFLOW ENGINE
# =========================

class WorkflowEngine:

    def __init__(self, handler_registry: TaskHandlerRegistry):
        self.handler_registry = handler_registry
        self.workflows: Dict[str, WorkflowDefinition] = {}
        self.executions: Dict[str, WorkflowExecution] = {}

    def register_workflow(self, workflow_id: str, tasks: List[TaskDefinition]) -> None:
        if len({task.task_id for task in tasks}) != len(tasks):
            raise ValueError("Duplicate task ids are not allowed")

        task_map = {task.task_id: task for task in tasks}
        topological_order = self._topological_sort(task_map)
        self.workflows[workflow_id] = WorkflowDefinition(
            workflow_id,
            task_map,
            topological_order,
        )

    def start(self, workflow_id: str) -> str:
        if workflow_id not in self.workflows:
            raise ValueError(f"Workflow not found: {workflow_id}")

        workflow = self.workflows[workflow_id]
        execution_id = str(uuid.uuid4())

        execution = WorkflowExecution(
            execution_id=execution_id,
            workflow=workflow,
            status=WorkflowStatus.RUNNING,
            task_executions={
                task_id: TaskExecution(task_id)
                for task_id in workflow.topological_order
            },
        )

        self.executions[execution_id] = execution
        self._run(execution)
        return execution_id

    def get_execution(self, execution_id: str) -> WorkflowExecution:
        return self.executions[execution_id]

    def _run(self, execution: WorkflowExecution) -> None:
        while execution.status == WorkflowStatus.RUNNING:
            ready_tasks = self._get_ready_tasks(execution)

            if not ready_tasks:
                break

            for task_execution in ready_tasks:
                self._execute_task(execution, task_execution)

        self._update_workflow_status(execution)

    def _get_ready_tasks(self, execution: WorkflowExecution) -> List[TaskExecution]:
        ready = []

        for task_id in execution.workflow.topological_order:
            task_execution = execution.task_executions[task_id]

            if task_execution.status != TaskStatus.PENDING:
                continue

            task_def = execution.workflow.tasks[task_id]
            dependencies_done = all(
                execution.task_executions[dep].status == TaskStatus.SUCCESS
                for dep in task_def.dependencies
            )

            if dependencies_done:
                ready.append(task_execution)

        return ready

    def _execute_task(
        self,
        execution: WorkflowExecution,
        task_execution: TaskExecution,
    ) -> None:
        task_def = execution.workflow.tasks[task_execution.task_id]
        handler = self.handler_registry.get(task_def.task_type)

        while task_execution.attempts < task_def.retry_policy.max_attempts:
            try:
                task_execution.status = TaskStatus.RUNNING
                task_execution.attempts += 1
                handler.execute(task_def)
                task_execution.status = TaskStatus.SUCCESS
                task_execution.error = None
                return
            except Exception as ex:
                task_execution.error = str(ex)

                if task_execution.attempts < task_def.retry_policy.max_attempts:
                    time.sleep(task_def.retry_policy.backoff_seconds)

        task_execution.status = TaskStatus.FAILED

    def _update_workflow_status(self, execution: WorkflowExecution) -> None:
        task_statuses = [
            task.status for task in execution.task_executions.values()
        ]

        if all(status == TaskStatus.SUCCESS for status in task_statuses):
            execution.status = WorkflowStatus.COMPLETED
        elif any(status == TaskStatus.FAILED for status in task_statuses):
            execution.status = WorkflowStatus.FAILED

    def _topological_sort(self, tasks: Dict[str, TaskDefinition]) -> List[str]:
        order = []
        visited = set()
        visiting = set()

        def dfs(task_id: str) -> None:
            if task_id in visiting:
                raise ValueError("Cycle detected in workflow")
            if task_id in visited:
                return
            if task_id not in tasks:
                raise ValueError(f"Unknown task dependency: {task_id}")

            visiting.add(task_id)

            for dependency in tasks[task_id].dependencies:
                dfs(dependency)

            visiting.remove(task_id)
            visited.add(task_id)
            order.append(task_id)

        for task_id in tasks:
            dfs(task_id)

        return order


# =========================
# DEMO
# =========================

def main():
    registry = TaskHandlerRegistry()
    registry.register("HTTP", HttpTaskHandler())
    registry.register("EMAIL", EmailTaskHandler())

    engine = WorkflowEngine(registry)

    fetch = TaskDefinition(
        task_id="fetch",
        task_type="HTTP",
        retry_policy=RetryPolicy(max_attempts=3, backoff_seconds=1),
    )

    notify = TaskDefinition(
        task_id="notify",
        task_type="EMAIL",
        dependencies=["fetch"],
        retry_policy=RetryPolicy(max_attempts=2, backoff_seconds=1),
    )

    engine.register_workflow("daily_etl", [fetch, notify])
    execution_id = engine.start("daily_etl")
    execution = engine.get_execution(execution_id)

    print("Workflow status:", execution.status.value)
    print("Task statuses:")
    for task in execution.task_executions.values():
        print(task.task_id, task.status.value, "attempts:", task.attempts)


if __name__ == "__main__":
    main()
