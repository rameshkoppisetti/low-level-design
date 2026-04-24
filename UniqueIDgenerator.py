import time
import threading


class SnowflakeIdGenerator:
    def __init__(self, machine_id: int):
        # Config
        self.epoch = 1700000000000  # custom epoch (ms)

        self.machine_id_bits = 10
        self.sequence_bits = 12

        self.max_sequence = (1 << self.sequence_bits) - 1

        # Inputs
        self.machine_id = machine_id

        # State
        self.last_timestamp = -1
        self.sequence = 0
        
        self.sequence_mask = (1 << self.sequence_bits) - 1
        self.machine_id_mask = (1 << self.machine_id_bits) - 1

        # Lock for concurrency
        self.lock = threading.Lock()

    def _current_time(self):
        return int(time.time() * 1000)

    def _wait_next_millis(self, timestamp):
        while True:
            current = self._current_time()
            if current > timestamp:
                return current

    def generate_id(self):
        with self.lock:
            current_timestamp = self._current_time()

            # ❗ Clock moved backwards
            if current_timestamp < self.last_timestamp:
                raise Exception("Clock moved backwards. Refusing to generate ID")

            # Same millisecond → increment sequence
            if current_timestamp == self.last_timestamp:
                self.sequence = (self.sequence + 1) & self.max_sequence

                # ❗ Sequence overflow
                if self.sequence == 0:
                    current_timestamp = self._wait_next_millis(current_timestamp)
            else:
                self.sequence = 0

            self.last_timestamp = current_timestamp

            # Construct ID
            return (
                ((current_timestamp - self.epoch) << (self.machine_id_bits + self.sequence_bits))
                | (self.machine_id << self.sequence_bits)
                | self.sequence
            )
    
    def decode(self, snowflake_id: int):
        # 1️⃣ Extract sequence (last 12 bits)
        sequence = snowflake_id & self.sequence_mask

        # 2️⃣ Extract machine ID (next 10 bits)
        machine_id = (snowflake_id >> self.sequence_bits) & self.machine_id_mask

        # 3️⃣ Extract timestamp (remaining higher bits)
        timestamp = snowflake_id >> (self.machine_id_bits + self.sequence_bits)
        timestamp += self.epoch

        return {
            "timestamp": timestamp,
            "machine_id": machine_id,
            "sequence": sequence
        }

generator = SnowflakeIdGenerator(machine_id=1)

for _ in range(5):
    print(generator.generate_id())