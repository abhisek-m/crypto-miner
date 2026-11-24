"""
CPU Mining Worker Engine
Provides full hardware control:
 - Thread count control (add / remove / limit threads)
 - CPU throttle duty cycle (10% to 100% utilization regulation)
 - Process priority management (Idle, Below Normal, Normal)
 - Live hashrate monitoring
"""

import os
import time
import struct
import hashlib
import threading
import psutil

# Process priority presets for Windows
PRIORITY_PRESETS = {
    "idle": psutil.IDLE_PRIORITY_CLASS,
    "below_normal": psutil.BELOW_NORMAL_PRIORITY_CLASS,
    "normal": psutil.NORMAL_PRIORITY_CLASS,
}

def dsha256(data: bytes) -> bytes:
    """Double SHA-256 hash."""
    return hashlib.sha256(hashlib.sha256(data).digest()).digest()

def build_merkle_root(coinbase_hash: bytes, merkle_branches: list) -> bytes:
    """Calculate Merkle root given coinbase hash and branches."""
    root = coinbase_hash
    for branch_hex in merkle_branches:
        branch = bytes.fromhex(branch_hex)
        root = dsha256(root + branch)
    return root

def parse_stratum_job(job_data: dict) -> dict:
    """Parse Stratum notify parameters into binary block header template and target integer."""
    try:
        job_id = job_data["job_id"]
        prevhash_hex = job_data["prevhash"]
        coinb1_hex = job_data["coinb1"]
        coinb2_hex = job_data["coinb2"]
        merkle_branch = job_data["merkle_branch"]
        version_hex = job_data["version"]
        nbits_hex = job_data["nbits"]
        ntime_hex = job_data["ntime"]
        extranonce1_hex = job_data.get("extranonce1", "")
        extranonce2_size = job_data.get("extranonce2_size", 4)
        difficulty = job_data.get("difficulty", 1.0)

        # Build extranonce2
        extranonce2_hex = "00" * extranonce2_size
        coinbase = bytes.fromhex(coinb1_hex + extranonce1_hex + extranonce2_hex + coinb2_hex)
        coinbase_hash = dsha256(coinbase)

        merkle_root = build_merkle_root(coinbase_hash, merkle_branch)

        # Base target (diff 1): 0x00000000FFFF...
        base_target = 0x00000000FFFF0000000000000000000000000000000000000000000000000000
        diff = max(0.00000001, float(difficulty))
        target_int = int(base_target / diff)

        version = bytes.fromhex(version_hex)
        prevhash = bytes.fromhex(prevhash_hex)
        ntime = bytes.fromhex(ntime_hex)
        nbits = bytes.fromhex(nbits_hex)

        header_prefix = version + prevhash + merkle_root + ntime + nbits
        header_suffix = b""

        return {
            "job_id": job_id,
            "extranonce2_hex": extranonce2_hex,
            "ntime_hex": ntime_hex,
            "header_prefix": header_prefix,
            "header_suffix": header_suffix,
            "target_int": target_int,
            "difficulty": difficulty
        }
    except Exception:
        return None

class CpuWorkerThread(threading.Thread):
    def __init__(self, thread_id, manager):
        super().__init__(daemon=True)
        self.thread_id = thread_id
        self.manager = manager
        self.running = True
        self.total_hashes = 0
        self.current_job = None
        self.nonce_start = (thread_id * 0x10000000) & 0xFFFFFFFF

    def stop(self):
        self.running = False

    def run(self):
        nonce = self.nonce_start
        batch_size = 5000  # Nonces evaluated per batch

        while self.running and self.manager.running:
            # Check pause state
            if self.manager.paused:
                time.sleep(0.1)
                continue

            job = self.manager.active_job
            if not job:
                time.sleep(0.05)
                continue

            target = job.get("target_int")
            header_prefix = job.get("header_prefix")
            header_suffix = job.get("header_suffix")
            job_id = job.get("job_id")
            extranonce2_hex = job.get("extranonce2_hex")
            ntime_hex = job.get("ntime_hex")

            if target is None or header_prefix is None or header_suffix is None:
                time.sleep(0.05)
                continue

            t_start = time.perf_counter()
            hashes_done = 0

            # Compute a batch of nonces
            for _ in range(batch_size):
                nonce = (nonce + 1) & 0xFFFFFFFF
                # Header: 76 bytes + 4 bytes nonce little-endian = 80 bytes
                header = header_prefix + struct.pack("<I", nonce) + header_suffix
                h = dsha256(header)
                # Check value against difficulty target (little-endian comparison)
                val = int.from_bytes(h, byteorder="little")
                hashes_done += 1

                if val < target:
                    # Valid share found!
                    nonce_hex = hex(nonce)[2:].zfill(8)
                    self.manager.on_share_found(job_id, extranonce2_hex, ntime_hex, nonce_hex)

            elapsed = time.perf_counter() - t_start
            self.total_hashes += hashes_done
            self.manager.record_hashes(hashes_done)

            # CPU Throttling / Duty Cycle Control:
            # Sleep proportionally based on throttle percentage
            throttle_pct = self.manager.throttle_pct
            if throttle_pct < 100 and throttle_pct > 0 and elapsed > 0:
                sleep_time = elapsed * ((100.0 - throttle_pct) / throttle_pct)
                if sleep_time > 0.0005:
                    time.sleep(min(sleep_time, 0.5))

class CpuWorkerManager:
    def __init__(self, target_threads=4, throttle_pct=75, priority="below_normal"):
        self.max_cores = os.cpu_count() or 4
        self.target_threads = max(1, min(target_threads, self.max_cores))
        self.throttle_pct = max(10, min(100, throttle_pct))
        self.priority_name = priority
        self.running = False
        self.paused = False

        self.workers = []
        self.active_job = None
        self.submit_callback = None

        # Hashrate metrics
        self.lock = threading.Lock()
        self.hash_count = 0
        self.last_metric_time = time.time()
        self.current_hashrate = 0.0
        self.total_hashes_all_time = 0

        self.set_priority(self.priority_name)

    def set_priority(self, priority_name):
        """Set Windows process priority class."""
        self.priority_name = priority_name.lower()
        priority_val = PRIORITY_PRESETS.get(self.priority_name, psutil.BELOW_NORMAL_PRIORITY_CLASS)
        try:
            p = psutil.Process(os.getpid())
            p.nice(priority_val)
        except Exception:
            pass

    def set_threads(self, n):
        """Dynamically adjust worker thread count."""
        n = max(1, min(n, self.max_cores))
        with self.lock:
            if n > len(self.workers):
                # Add threads
                for i in range(len(self.workers), n):
                    w = CpuWorkerThread(i, self)
                    self.workers.append(w)
                    if self.running:
                        w.start()
            elif n < len(self.workers):
                # Remove threads
                to_remove = self.workers[n:]
                self.workers = self.workers[:n]
                for w in to_remove:
                    w.stop()
            self.target_threads = n

    def add_thread(self):
        if self.target_threads < self.max_cores:
            self.set_threads(self.target_threads + 1)
            return True
        return False

    def remove_thread(self):
        if self.target_threads > 1:
            self.set_threads(self.target_threads - 1)
            return True
        return False

    def set_throttle(self, pct):
        """Set CPU duty cycle throttling (10 to 100%)."""
        self.throttle_pct = max(10, min(100, int(pct)))

    def set_job(self, job_data):
        """Prepare block header templates for worker threads."""
        parsed = parse_stratum_job(job_data)
        if parsed:
            self.active_job = parsed

    def on_share_found(self, job_id, extranonce2_hex, ntime_hex, nonce_hex):
        if self.submit_callback:
            self.submit_callback(job_id, extranonce2_hex, ntime_hex, nonce_hex)

    def record_hashes(self, count):
        with self.lock:
            self.hash_count += count
            self.total_hashes_all_time += count

    def update_metrics(self):
        """Update and return smoothed hashrate."""
        now = time.time()
        dt = now - self.last_metric_time
        if dt >= 0.8:
            with self.lock:
                self.current_hashrate = self.hash_count / dt
                self.hash_count = 0
                self.last_metric_time = now
        return self.current_hashrate

    def start(self):
        self.running = True
        self.paused = False
        self.set_threads(self.target_threads)
        for w in self.workers:
            if not w.is_alive():
                w.start()

    def pause(self):
        self.paused = not self.paused
        return self.paused

    def stop(self):
        self.running = False
        for w in self.workers:
            w.stop()
        self.workers.clear()
