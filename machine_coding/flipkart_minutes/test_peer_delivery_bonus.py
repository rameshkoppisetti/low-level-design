import unittest
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[2]))

from machine_coding.flipkart_minutes.peer_delivery_bonus import (
    CustomerRepository,
    DeliveryCountRankingStrategy,
    DriverRepository,
    InvalidStateError,
    NotificationService,
    NotificationVendor,
    OrderRepository,
    OrderStatus,
    PeerDeliveryService,
    RatingRankingStrategy,
    ValidationError,
)


class SilentVendor(NotificationVendor):
    def send(self, recipient_id: str, message: str) -> None:
        pass


def create_service() -> PeerDeliveryService:
    return PeerDeliveryService(
        CustomerRepository(),
        DriverRepository(),
        OrderRepository(),
        {"documents", "food", "medicine"},
        NotificationService([SilentVendor()]),
    )


class PeerDeliveryBonusTest(unittest.TestCase):
    def test_assignment_queue_and_completion(self):
        service = create_service()
        service.onboard_customer("c1", "Anu")
        service.onboard_customer("c2", "Bala")
        service.onboard_driver("d1", "Driver One")

        order_1 = service.place_order("c1", "documents")
        order_2 = service.place_order("c2", "food")

        self.assertEqual(OrderStatus.ASSIGNED, order_1.status)
        self.assertEqual(OrderStatus.QUEUED, order_2.status)

        service.pickup_order("d1", order_1.order_id)
        service.complete_order("d1", order_1.order_id)

        self.assertEqual(OrderStatus.ASSIGNED, order_2.status)

    def test_unsupported_item_rejected(self):
        service = create_service()
        service.onboard_customer("c1", "Anu")

        with self.assertRaises(ValidationError):
            service.place_order("c1", "laptop")

    def test_cancel_after_pickup_rejected(self):
        service = create_service()
        service.onboard_customer("c1", "Anu")
        service.onboard_driver("d1", "Driver One")

        order = service.place_order("c1", "documents")
        service.pickup_order("d1", order.order_id)

        with self.assertRaises(InvalidStateError):
            service.cancel_order(order.order_id)

    def test_rating_and_dashboards(self):
        service = create_service()
        service.onboard_customer("c1", "Anu")
        service.onboard_driver("d1", "Driver One")

        order = service.place_order("c1", "documents")
        service.pickup_order("d1", order.order_id)
        service.complete_order("d1", order.order_id)
        service.rate_driver("c1", order.order_id, 5)

        self.assertEqual([("d1", 1, 5.0)], service.top_drivers(RatingRankingStrategy()))
        self.assertEqual(
            [("d1", 1, 5.0)],
            service.top_drivers(DeliveryCountRankingStrategy()),
        )

    def test_auto_cancel_assigned_order_before_pickup(self):
        service = create_service()
        service.onboard_customer("c1", "Anu")
        service.onboard_customer("c2", "Bala")
        service.onboard_driver("d1", "Driver One")

        order_1 = service.place_order("c1", "documents")
        order_2 = service.place_order("c2", "food")
        order_2.created_at = order_1.created_at + PeerDeliveryService.AUTO_CANCEL_SECONDS

        service.auto_cancel_expired_orders(
            now=order_1.created_at + PeerDeliveryService.AUTO_CANCEL_SECONDS + 1
        )

        self.assertEqual(OrderStatus.CANCELED, order_1.status)
        self.assertEqual(OrderStatus.ASSIGNED, order_2.status)


if __name__ == "__main__":
    unittest.main()
