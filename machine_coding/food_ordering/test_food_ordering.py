import unittest
from concurrent.futures import ThreadPoolExecutor, as_completed

from machine_coding.food_ordering.food_ordering import (
    AddRestaurantRequest,
    ChangeMenuRequest,
    FoodOrderingApp,
    OrderRejectedError,
    PlaceOrderRequest,
    ValidationError,
    seed_data,
)


class FoodOrderingTest(unittest.TestCase):
    def setUp(self):
        self.app = FoodOrderingApp()
        seed_data(self.app)

    def test_sample_order_flow(self):
        order_1 = self.app.order_service.place_order(
            PlaceOrderRequest(["Idly", "Poori"])
        )
        self.assertEqual(["Eat Fit", "Rasaganga"], order_1.restaurants())

        order_2 = self.app.order_service.place_order(
            PlaceOrderRequest(["Idly", "Vada"])
        )
        self.assertEqual(["A2B", "Eat Fit"], order_2.restaurants())

        self.assertEqual(
            {
                "A2B": 3,
                "Rasaganga": 5,
                "Eat Fit": 0,
            },
            self.app.stats_service.print_stats(),
        )

        order_3 = self.app.order_service.place_order(PlaceOrderRequest(["Idly"]))
        self.assertEqual(["A2B"], order_3.restaurants())

        self.app.order_service.fulfill_order(order_1.order_id)

        self.assertEqual(
            {
                "A2B": 2,
                "Rasaganga": 6,
                "Eat Fit": 1,
            },
            self.app.stats_service.print_stats(),
        )

        self.app.order_service.fulfill_order(order_2.order_id)
        self.app.restaurant_service.change_menu(
            ChangeMenuRequest("Eat Fit", {"Idly": 60, "Vada": 40}, 2)
        )

        order_4 = self.app.order_service.place_order(PlaceOrderRequest(["Idly"]))
        self.assertEqual(["A2B"], order_4.restaurants())

    def test_order_rejected_when_item_unavailable(self):
        with self.assertRaises(OrderRejectedError):
            self.app.order_service.place_order(PlaceOrderRequest(["Pizza"]))

    def test_duplicate_restaurant_rejected(self):
        with self.assertRaises(ValidationError):
            self.app.restaurant_service.add_restaurant(
                AddRestaurantRequest("A2B", {"Coffee": 20}, 2)
            )

    def test_capacity_replenished_on_fulfillment(self):
        order = self.app.order_service.place_order(PlaceOrderRequest(["Idly"]))
        self.assertEqual(1, self.app.stats_service.print_stats()["Eat Fit"])

        self.app.order_service.fulfill_order(order.order_id)

        self.assertEqual(2, self.app.stats_service.print_stats()["Eat Fit"])

    def test_change_menu_replaces_prices(self):
        self.app.restaurant_service.change_menu(
            ChangeMenuRequest("Eat Fit", {"Idly": 60, "Vada": 40}, 2)
        )

        order = self.app.order_service.place_order(PlaceOrderRequest(["Idly"]))

        self.assertEqual(["A2B"], order.restaurants())

    def test_concurrent_orders_do_not_overbook_restaurant(self):
        app = FoodOrderingApp()
        app.restaurant_service.add_restaurant(
            AddRestaurantRequest("Only Idly", {"Idly": 10}, 1)
        )

        def try_order():
            try:
                app.order_service.place_order(PlaceOrderRequest(["Idly"]))
                return True
            except OrderRejectedError:
                return False

        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(try_order) for _ in range(5)]

        results = [future.result() for future in as_completed(futures)]

        self.assertEqual(1, results.count(True))
        self.assertEqual(4, results.count(False))
        self.assertEqual({"Only Idly": 0}, app.stats_service.print_stats())


if __name__ == "__main__":
    unittest.main()
