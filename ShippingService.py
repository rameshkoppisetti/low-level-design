class ShippingService:
    def __init__(self):
        # courier -> from -> to -> cost
        self.graph = {}

    def load_routes(self, routes):
        for route in routes:
            frm, to, cost, courier = route.split(",")
            self.add_route(frm, to, int(cost), courier)

    def add_route(self, frm, to, cost, courier):
        self.graph.setdefault(courier, {}).setdefault(frm, {})[to] = cost

    def remove_route(self, frm, to, courier):
        if courier not in self.graph:
            return

        if frm not in self.graph[courier]:
            return

        self.graph[courier][frm].pop(to, None)

        if not self.graph[courier][frm]:
            del self.graph[courier][frm]

        if not self.graph[courier]:
            del self.graph[courier]

    def find_shipping_cost(self, query):
        """
        query:
        Part-1: "US CA DHL"
        Part-3: "US MX"
        """

        parts = query.split()

        if len(parts) == 3:
            frm, to, required_courier = parts
            couriers = [required_courier]
        else:
            frm, to = parts
            couriers = self.graph.keys()

        best_cost = float("inf")
        best_path = None
        best_courier = None

        for courier in couriers:
            provider = self.graph.get(courier)

            if not provider or frm not in provider:
                continue

            for nxt, cost1 in provider[frm].items():

                # Direct route
                if nxt == to and cost1 < best_cost:
                    best_cost = cost1
                    best_path = f"{frm}->{to}"
                    best_courier = courier

                # One transit
                for dest, cost2 in provider.get(nxt, {}).items():
                    if dest == to and cost1 + cost2 < best_cost:
                        best_cost = cost1 + cost2
                        best_path = f"{frm}->{nxt}->{to}"
                        best_courier = courier

        if best_path is None:
            return -1

        return f"{best_path}, {best_courier}, {best_cost}"
Example Usage
service = ShippingService()

service.load_routes([
    "US,CA,10,DHL",
    "CA,MX,15,DHL",
    "US,CA,8,UPS",
    "CA,MX,20,UPS",
    "US,MX,40,FedEx"
])

print(service.find_shipping_cost("US MX DHL"))
# US->CA->MX, DHL, 25

print(service.find_shipping_cost("US MX"))
# US->CA->MX, DHL, 25

service.add_route("US", "MX", 18, "UPS")
print(service.find_shipping_cost("US MX"))
# US->MX, UPS, 18

service.remove_route("US", "MX", "UPS")
print(service.find_shipping_cost("US MX"))
# US->CA->MX, DHL, 25
