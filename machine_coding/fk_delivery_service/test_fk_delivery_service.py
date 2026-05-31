import unittest
from datetime import datetime
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[2]))

from machine_coding.fk_delivery_service.fk_delivery_service import (
    DeliveryApp,
    OrderStatus,
    ValidationError,
)


class FKDeliveryServiceTest(unittest.TestCase):
    def test_sample_flow(self):
        app = DeliveryApp()
        service = app.delivery_service

        service.create_order("Order A", "560087")
        service.create_order("Order B", "560088")
        service.create_order("Order C", "560089")
        service.create_order("Order D", "560087")
        service.create_agent("Agent A", "560087")
        service.create_agent("Agent B", "560088")
        service.create_agent("Agent C", "560089")

        self.assertEqual(
            [
                "Agent A has picked up Order A",
                "Agent A has delivered Order A to 560087",
                "Agent B has picked up Order B",
                "Agent B has delivered Order B to 560088",
                "Agent C has picked up Order C",
                "Agent C has delivered Order C to 560089",
                "Agent A has picked up Order D",
                "Agent A has delivered Order D to 560087",
            ],
            service.execute_deliveries(),
        )

    def test_order_without_agent_stays_pending(self):
        app = DeliveryApp()
        service = app.delivery_service

        service.create_order("Order A", "560087")

        self.assertEqual([], service.execute_deliveries())
        self.assertEqual(OrderStatus.CREATED, app.order_repo.get("Order A").status)

    def test_multi_pincode_agent(self):
        app = DeliveryApp()
        service = app.delivery_service

        service.create_order("Order A", "560087")
        service.create_order("Order B", "560088")
        service.create_agent("Agent A", ["560087", "560088"])

        logs = service.execute_deliveries()

        self.assertEqual("Agent A has picked up Order A", logs[0])
        self.assertEqual("Agent A has picked up Order B", logs[2])

    def test_scheduled_delivery_logs_time(self):
        app = DeliveryApp()
        service = app.delivery_service
        scheduled_at = datetime(2025, 3, 22, 10, 30)

        service.create_order("Order A", "560087", scheduled_at, 30)
        service.create_agent("Agent A", "560087")

        self.assertEqual(
            [
                "Agent A has picked up Order A at 10:30 AM, Mar 22, 2025",
                (
                    "Agent A has completed delivery of Order A "
                    "to 560087 at 11:00 AM, Mar 22, 2025"
                ),
            ],
            service.execute_deliveries(),
        )

    def test_invalid_duration_rejected(self):
        app = DeliveryApp()

        with self.assertRaises(ValidationError):
            app.delivery_service.create_order("Order A", "560087", None, -1)


if __name__ == "__main__":
    unittest.main()
