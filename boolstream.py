import threading


class BoolDS:
    def __init__(self):
        # Atomic global snapshot: (value, version)
        self.global_state = (False, 0)
        self.global_lock = threading.Lock()

        # Per-index overrides
        self.values = {}
        self.values_lock = threading.Lock()

    # -------------------
    # GLOBAL OPERATIONS
    # -------------------

    def setAllTrue(self):
        # Step 1: update global
        with self.global_lock:
            _, version = self.global_state
            self.global_state = (True, version + 1)

        # Step 2: clear overrides (separate lock → no deadlock)
        with self.values_lock:
            self.values.clear()

    def setAllFalse(self):
        with self.global_lock:
            _, version = self.global_state
            self.global_state = (False, version + 1)

        with self.values_lock:
            self.values.clear()

    # -------------------
    # PER INDEX
    # -------------------

    def setTrue(self, index):
        # atomic snapshot read
        _, version = self.global_state

        with self.values_lock:
            self.values[index] = (True, version)

    def setFalse(self, index):
        _, version = self.global_state

        with self.values_lock:
            self.values[index] = (False, version)

    # -------------------
    # READ
    # -------------------

    def getIndex(self, index):
        # atomic snapshot read
        g_val, g_ver = self.global_state

        with self.values_lock:
            override = self.values.get(index)

        if override is None:
            return g_val

        val, ver = override

        # only valid if same version
        if ver == g_ver:
            return val

        return g_val


# -------------------
# DEMO
# -------------------

if __name__ == "__main__":
    ds = BoolDS()

    ds.setTrue(1)
    print(ds.getIndex(1))  # True

    ds.setAllFalse()
    print(ds.getIndex(1))  # False

    ds.setTrue(1)
    print(ds.getIndex(1))  # True

    ds.setAllTrue()
    print(ds.getIndex(1))  # True