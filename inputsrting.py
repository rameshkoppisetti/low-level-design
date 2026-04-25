import heapq
import os

CHUNK_SIZE = 1000       # number of integers per chunk
BUFFER_SIZE = 4096      # bytes for buffered I/O
MERGE_FACTOR = 10       # k-way merge


# -------- STEP 1: CREATE SORTED RUNS --------
def create_sorted_runs(input_file):
    runs = []
    with open(input_file, 'r') as f:
        while True:
            chunk = f.readlines(CHUNK_SIZE)
            if not chunk:
                break

            nums = [int(x.strip()) for x in chunk]
            nums.sort()

            run_file = f"run_{len(runs)}.txt"
            with open(run_file, 'w') as rf:
                rf.writelines(f"{num}\n" for num in nums)

            runs.append(run_file)

    return runs


# -------- BUFFERED READER --------
class BufferedFileReader:
    def __init__(self, filename):
        self.file = open(filename, 'r')
        self.buffer = []
        self._fill()

    def _fill(self):
        self.buffer = self.file.readlines(BUFFER_SIZE)

    def next(self):
        if not self.buffer:
            return None

        val = self.buffer.pop(0)

        if not self.buffer:
            self._fill()

        return int(val.strip()) if val else None

    def close(self):
        self.file.close()


# -------- STEP 2: K-WAY MERGE (BUFFERED) --------
def merge_runs(run_files, output_file):
    readers = [BufferedFileReader(f) for f in run_files]
    min_heap = []

    # initialize heap
    for i, reader in enumerate(readers):
        val = reader.next()
        if val is not None:
            heapq.heappush(min_heap, (val, i))

    with open(output_file, 'w', buffering=BUFFER_SIZE) as out:
        output_buffer = []

        while min_heap:
            val, idx = heapq.heappop(min_heap)
            output_buffer.append(f"{val}\n")

            # flush periodically
            if len(output_buffer) >= 1000:
                out.writelines(output_buffer)
                output_buffer.clear()

            next_val = readers[idx].next()
            if next_val is not None:
                heapq.heappush(min_heap, (next_val, idx))

        # final flush
        if output_buffer:
            out.writelines(output_buffer)

    # cleanup
    for r in readers:
        r.close()
    for f in run_files:
        os.remove(f)


# -------- STEP 3: MULTI-PASS MERGE --------
def multi_pass_merge(run_files, output_file, k=MERGE_FACTOR):
    round_num = 0

    while len(run_files) > 1:
        new_runs = []

        for i in range(0, len(run_files), k):
            batch = run_files[i:i+k]
            merged_file = f"merged_{round_num}_{i}.txt"

            merge_runs(batch, merged_file)
            new_runs.append(merged_file)

        run_files = new_runs
        round_num += 1

    os.rename(run_files[0], output_file)


# -------- DRIVER --------
def external_merge_sort(input_file, output_file):
    runs = create_sorted_runs(input_file)
    multi_pass_merge(runs, output_file)


# -------- USAGE --------
if __name__ == "__main__":
    external_merge_sort("input.txt", "sorted_output.txt")