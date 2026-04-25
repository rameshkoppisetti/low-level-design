from collections import defaultdict, deque


# =========================
# PACKAGE MODEL
# =========================

class Package:
    def __init__(self, name):
        self.name = name

    def __repr__(self):
        return self.name


# =========================
# PACKAGE MANAGER
# =========================

class PackageManager:

    def __init__(self):
        self.graph = defaultdict(list)   # dependency graph
        self.in_degree = defaultdict(int)
        self.packages = set()

    # If pkg depends on dep
    def add_dependency(self, pkg: Package, dep: Package):
        # Edge: dep → pkg
        self.graph[dep.name].append(pkg.name)
        self.in_degree[pkg.name] += 1

        self.packages.add(pkg.name)
        self.packages.add(dep.name)

    def install(self, target: Package):

        # Step 1: Build local copies (so we don't modify original graph)
        in_degree = dict(self.in_degree)
        graph = self.graph

        queue = deque()
        install_order = []

        # Step 2: Add nodes with in-degree 0
        for pkg in self.packages:
            if in_degree.get(pkg, 0) == 0:
                queue.append(pkg)

        # Step 3: BFS
        while queue:
            current = queue.popleft()
            install_order.append(current)

            for neighbor in graph[current]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        # Step 4: Cycle detection
        if len(install_order) != len(self.packages):
            raise Exception("Cyclic dependency detected!")

        print("Install Order:")
        for pkg in install_order:
            print(f"Installing {pkg}")

def main():
    manager = PackageManager()

    A = Package("A")
    B = Package("B")
    C = Package("C")
    D = Package("D")

    manager.add_dependency(A, B)  # A depends on B
    manager.add_dependency(A, C)
    manager.add_dependency(B, D)

    manager.install(A)


if __name__ == "__main__":
    main()