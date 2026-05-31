import unittest
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[2]))

from machine_coding.flipkart_minutes.flipkart_minutes import (
    CustomerRepository,
    FlipkartMinutesService,
    InvalidStateError,
    OrderRepository,
    OrderStatus,
    PartnerRepository,
    PartnerStatus,
)


def create_service() -> FlipkartMinutesService:
    return FlipkartMinutesService(
        CustomerRepository(),
        PartnerRepository(),
        OrderRepository(),
    )


class FlipkartMinutesTest(unittest.TestCase):
    def test_assignment_and_queue(self):
        service = create_service()
        service.onboard_customer("c1", "Anu")
        service.onboard_customer("c2", "Bala")
        service.onboard_delivery_partner("p1", "Partner One")

        order_1 = service.place_order("c1", "Milk")
        order_2 = service.place_order("c2", "Bread")

        self.assertEqual(OrderStatus.ASSIGNED, order_1.status)
        self.assertEqual(OrderStatus.QUEUED, order_2.status)

        service.pickup_order("p1", order_1.order_id)
        service.complete_order("p1", order_1.order_id)

        self.assertEqual(OrderStatus.ASSIGNED, order_2.status)
        self.assertEqual("p1", order_2.partner_id)

    def test_cancel_assigned_order_before_pickup_reassigns_partner(self):
        service = create_service()
        service.onboard_customer("c1", "Anu")
        service.onboard_customer("c2", "Bala")
        service.onboard_delivery_partner("p1", "Partner One")

        order_1 = service.place_order("c1", "Milk")
        order_2 = service.place_order("c2", "Bread")

        service.cancel_order(order_1.order_id)

        self.assertEqual(OrderStatus.CANCELED, order_1.status)
        self.assertEqual(OrderStatus.ASSIGNED, order_2.status)
        self.assertEqual("p1", order_2.partner_id)

    def test_cancel_is_idempotent_for_already_canceled_order(self):
        service = create_service()
        service.onboard_customer("c1", "Anu")

        order = service.place_order("c1", "Milk")

        service.cancel_order(order.order_id)
        service.cancel_order(order.order_id)

        self.assertEqual(OrderStatus.CANCELED, order.status)

    def test_cannot_cancel_after_pickup(self):
        service = create_service()
        service.onboard_customer("c1", "Anu")
        service.onboard_delivery_partner("p1", "Partner One")

        order = service.place_order("c1", "Milk")
        service.pickup_order("p1", order.order_id)

        with self.assertRaises(InvalidStateError):
            service.cancel_order(order.order_id)

    def test_wrong_partner_cannot_pickup(self):
        service = create_service()
        service.onboard_customer("c1", "Anu")
        service.onboard_delivery_partner("p1", "Partner One")
        service.onboard_delivery_partner("p2", "Partner Two")

        order = service.place_order("c1", "Milk")

        with self.assertRaises(InvalidStateError):
            service.pickup_order("p2", order.order_id)

    def test_multiple_orders_with_two_partners(self):
        service = create_service()
        service.onboard_customer("c1", "Anu")
        service.onboard_delivery_partner("p1", "Partner One")
        service.onboard_delivery_partner("p2", "Partner Two")

        order_1 = service.place_order("c1", "Milk")
        order_2 = service.place_order("c1", "Bread")
        order_3 = service.place_order("c1", "Eggs")

        self.assertEqual(OrderStatus.ASSIGNED, order_1.status)
        self.assertEqual(OrderStatus.ASSIGNED, order_2.status)
        self.assertEqual(OrderStatus.QUEUED, order_3.status)

    def test_stale_partner_entry_does_not_drop_queued_order(self):
        service = create_service()
        service.onboard_customer("c1", "Anu")
        service.onboard_delivery_partner("p1", "Partner One")

        partner = service.partner_repo.get("p1")
        partner.status = PartnerStatus.ASSIGNED
        order = service.place_order("c1", "Milk")

        self.assertEqual(OrderStatus.QUEUED, order.status)

        partner.status = PartnerStatus.AVAILABLE
        service.available_partners.append("p1")
        service._assign_orders_locked()

        self.assertEqual(OrderStatus.ASSIGNED, order.status)

    def test_concurrent_orders_do_not_assign_one_partner_to_multiple_orders(self):
        service = create_service()
        service.onboard_delivery_partner("p1", "Partner One")
        for index in range(5):
            service.onboard_customer(f"c{index}", f"Customer {index}")

        def place(index: int) -> OrderStatus:
            return service.place_order(f"c{index}", "Milk").status

        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(place, index) for index in range(5)]

        statuses = [future.result() for future in as_completed(futures)]

        self.assertEqual(1, statuses.count(OrderStatus.ASSIGNED))
        self.assertEqual(4, statuses.count(OrderStatus.QUEUED))
        self.assertEqual(PartnerStatus.ASSIGNED, service.get_delivery_partner_status("p1"))


if __name__ == "__main__":
    unittest.main()
