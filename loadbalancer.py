from abc import ABC, abstractmethod
import random


# ---------------- SERVER ---------------- #

class Server:
    def __init__(self, server_id):
        self.server_id = server_id
        self.is_alive = True
        self.active_connections = 0

    def handle_request(self, request):
        if not self.is_alive:
            raise Exception(f"{self.server_id} is down")

        self.active_connections += 1
        response = f"{self.server_id} handled {request}"
        self.active_connections -= 1

        return response


# ---------------- STRATEGY INTERFACE ---------------- #

class LoadBalancingStrategy(ABC):
    @abstractmethod
    def select_server(self, servers):
        pass


# ---------------- ROUND ROBIN ---------------- #

class RoundRobinStrategy(LoadBalancingStrategy):
    def __init__(self):
        self.index = 0

    def select_server(self, servers):
        if not servers:
            raise Exception("No healthy servers available")

        server = servers[self.index % len(servers)]
        self.index += 1
        return server


# ---------------- LEAST CONNECTIONS ---------------- #

class LeastConnectionsStrategy(LoadBalancingStrategy):
    def select_server(self, servers):
        if not servers:
            raise Exception("No healthy servers available")

        return min(servers, key=lambda s: s.active_connections)


# ---------------- HEALTH MONITOR ---------------- #

class HealthMonitor:
    def __init__(self, servers):
        self.servers = servers

    def check_server(self, server):
        """
        Simulate health check.
        In real systems:
        - HTTP ping (/health)
        - TCP connection check
        """
        # Simulate random failure/recovery
        return random.choice([True, True, True, False])  # mostly healthy

    def run_health_check(self):
        """
        Update health status of all servers
        """
        for server in self.servers:
            is_healthy = self.check_server(server)
            server.is_alive = is_healthy


# ---------------- LOAD BALANCER ---------------- #

class LoadBalancer:
    def __init__(self, strategy: LoadBalancingStrategy):
        self.servers = []
        self.strategy = strategy

    def add_server(self, server: Server):
        self.servers.append(server)

    def remove_server(self, server: Server):
        if server in self.servers:
            self.servers.remove(server)

    def set_strategy(self, strategy: LoadBalancingStrategy):
        self.strategy = strategy

    def get_healthy_servers(self):
        return [s for s in self.servers if s.is_alive]

    def route_request(self, request):
        healthy_servers = self.get_healthy_servers()

        if not healthy_servers:
            raise Exception("No healthy servers available")

        server = self.strategy.select_server(healthy_servers)
        return server.handle_request(request)


# ---------------- TEST CASES ---------------- #

if name == "__main__":
    # Create servers
    s1 = Server("S1")
    s2 = Server("S2")
    s3 = Server("S3")

    # Load balancer
    lb = LoadBalancer(RoundRobinStrategy())
    lb.add_server(s1)
    lb.add_server(s2)
    lb.add_server(s3)

    # Health monitor
    monitor = HealthMonitor(lb.servers)

    print("---- Initial Requests ----")
    for i in range(5):
        print(lb.route_request(f"Req-{i}"))

    print("\n---- Running Health Check ----")
    monitor.run_health_check()

    # Show server status
    for s in lb.servers:
        print(f"{s.server_id} is_alive = {s.is_alive}")

    print("\n---- Requests After Health Check ----")
    for i in range(5):
        try:
            print(lb.route_request(f"Req-{i}"))
        except Exception as e:
            print("Error:", e)