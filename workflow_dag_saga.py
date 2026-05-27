import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List


class StepStatus:
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    COMPENSATED = "COMPENSATED"


class Step:
    def __init__(self, step_id: str, max_retries: int):
        self.id = step_id
        self.max_retries = max_retries

    def execute(self, context: dict) -> bool:
        raise NotImplementedError

    def compensate(self, context: dict) -> None:
        raise NotImplementedError


class OrderStep(Step):
    def execute(self, context: dict) -> bool:
        print(f"[STEP] Executing OrderStep: {self.id}")
        context["order.registered"] = True
        return True

    def compensate(self, context: dict) -> None:
        print(f"[COMPENSATION] Deleting order registration from OrderStep: {self.id}")


class PaymentStep(Step):
    def __init__(self, step_id: str, max_retries: int, should_fail: bool):
        super().__init__(step_id, max_retries)
        self.should_fail = should_fail

    def execute(self, context: dict) -> bool:
        print(f"[STEP] Executing PaymentStep: {self.id}")
        if self.should_fail:
            raise RuntimeError("Payment gateway timeout.")
        context["payment.txId"] = "TX-PY-202"
        return True

    def compensate(self, context: dict) -> None:
        print(
            "[COMPENSATION] Refunding transaction "
            f"{context.get('payment.txId')} via PaymentStep: {self.id}"
        )


class InventoryStep(Step):
    def __init__(self, step_id: str, max_retries: int, should_fail: bool):
        super().__init__(step_id, max_retries)
        self.should_fail = should_fail

    def execute(self, context: dict) -> bool:
        print(f"[STEP] Executing InventoryStep: {self.id}")
        if self.should_fail:
            raise RuntimeError("Inventory reserve error.")
        context["inventory.reserved"] = True
        return True

    def compensate(self, context: dict) -> None:
        print(f"[COMPENSATION] Releasing inventory reservations in InventoryStep: {self.id}")


class ShipmentStep(Step):
    def execute(self, context: dict) -> bool:
        print(f"[STEP] Executing ShipmentStep: {self.id}")
        context["shipment.carrier"] = "FedEx"
        return True

    def compensate(self, context: dict) -> None:
        print(f"[COMPENSATION] Canceling shipment request via ShipmentStep: {self.id}")


class DAGSagaScheduler:
    def __init__(self, max_workers: int = 4):
        self.steps: Dict[str, Step] = {}
        self.adj_list: Dict[str, List[str]] = {}
        self.parents: Dict[str, List[str]] = {}
        self.step_status: Dict[str, str] = {}
        self.completed_steps: List[str] = []
        self.max_workers = max_workers
        self.context_lock = threading.RLock()

    def add_step(self, step: Step) -> None:
        if step.id in self.steps:
            raise ValueError(f"Duplicate step id: {step.id}")

        self.steps[step.id] = step
        self.adj_list.setdefault(step.id, [])
        self.parents.setdefault(step.id, [])
        self.step_status[step.id] = StepStatus.PENDING

    def add_dependency(self, parent_id: str, child_id: str) -> None:
        if parent_id not in self.steps:
            raise ValueError(f"Unknown parent step: {parent_id}")
        if child_id not in self.steps:
            raise ValueError(f"Unknown child step: {child_id}")

        self.adj_list[parent_id].append(child_id)
        self.parents[child_id].append(parent_id)

    def execute_workflow(self) -> bool:
        print("=== Starting Python Workflow DAG Execution ===")

        self._validate_dag()

        context = {}
        completed = set()
        failed = False

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            while len(completed) < len(self.steps):
                ready_steps = self._get_ready_steps(completed)

                if not ready_steps:
                    failed = True
                    break

                futures = {
                    executor.submit(self._execute_step_with_retry, step_id, context): step_id
                    for step_id in ready_steps
                }

                batch_failed = False

                for future in as_completed(futures):
                    step_id = futures[future]
                    success = future.result()

                    if success:
                        completed.add(step_id)
                    else:
                        batch_failed = True

                if batch_failed:
                    failed = True
                    break

        if failed:
            self._rollback(context)
            return False

        print("\n[SUCCESS] Workflow completed successfully!")
        return True

    def _get_ready_steps(self, completed: set) -> List[str]:
        ready = []

        for step_id in self.steps:
            if self.step_status[step_id] != StepStatus.PENDING:
                continue

            if all(parent_id in completed for parent_id in self.parents[step_id]):
                ready.append(step_id)

        return ready

    def _execute_step_with_retry(self, step_id: str, context: dict) -> bool:
        step = self.steps[step_id]
        self.step_status[step_id] = StepStatus.RUNNING
        total_attempts = step.max_retries + 1

        for attempt in range(1, total_attempts + 1):
            try:
                with self.context_lock:
                    success = step.execute(context)

                if success:
                    self.step_status[step_id] = StepStatus.COMPLETED
                    self.completed_steps.append(step_id)
                    return True
            except Exception as ex:
                print(f"  [RETRY] Step {step_id} failed attempt {attempt}: {ex}")

        self.step_status[step_id] = StepStatus.FAILED
        print(f"[FAILED] Step {step_id} failed permanently.")
        return False

    def _rollback(self, context: dict) -> None:
        print("\n[SAGA TRIGGERED] Workflow failed. Executing compensation rollback...")

        for step_id in reversed(self.completed_steps):
            step = self.steps[step_id]
            with self.context_lock:
                step.compensate(context)
            self.step_status[step_id] = StepStatus.COMPENSATED

    def _validate_dag(self) -> None:
        visited = set()
        visiting = set()

        def dfs(step_id: str) -> None:
            if step_id in visiting:
                raise ValueError("Cycle detected in workflow DAG")
            if step_id in visited:
                return

            visiting.add(step_id)

            for child_id in self.adj_list.get(step_id, []):
                dfs(child_id)

            visiting.remove(step_id)
            visited.add(step_id)

        for step_id in self.steps:
            dfs(step_id)


if __name__ == "__main__":
    print("--- Scenario 1: Successful DAG execution ---")
    success_scheduler = DAGSagaScheduler()

    order = OrderStep("order", 1)
    payment = PaymentStep("payment", 2, False)
    inventory = InventoryStep("inventory", 1, False)
    shipment = ShipmentStep("shipment", 1)

    success_scheduler.add_step(order)
    success_scheduler.add_step(payment)
    success_scheduler.add_step(inventory)
    success_scheduler.add_step(shipment)

    success_scheduler.add_dependency("order", "payment")
    success_scheduler.add_dependency("order", "inventory")
    success_scheduler.add_dependency("payment", "shipment")
    success_scheduler.add_dependency("inventory", "shipment")

    success_scheduler.execute_workflow()

    print("\n--- Scenario 2: Failed DAG execution with Saga compensation rollback ---")
    failure_scheduler = DAGSagaScheduler()

    order_fail = OrderStep("order", 1)
    payment_fail = PaymentStep("payment", 2, False)
    inventory_fail = InventoryStep("inventory", 2, True)
    shipment_fail = ShipmentStep("shipment", 1)

    failure_scheduler.add_step(order_fail)
    failure_scheduler.add_step(payment_fail)
    failure_scheduler.add_step(inventory_fail)
    failure_scheduler.add_step(shipment_fail)

    failure_scheduler.add_dependency("order", "payment")
    failure_scheduler.add_dependency("order", "inventory")
    failure_scheduler.add_dependency("payment", "shipment")
    failure_scheduler.add_dependency("inventory", "shipment")

    failure_scheduler.execute_workflow()
