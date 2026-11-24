"""
GPU Hardware Controller & Monitor
Interfaces with NVIDIA GeForce RTX 2050 via nvidia-smi and system drivers.
Controls GPU intensity and power metrics.
"""

import subprocess
import shutil
import time
import threading
from worker_cpu import parse_stratum_job

class GpuHardwareMonitor:
    def __init__(self, device_id=0):
        self.device_id = device_id
        self.has_nvidia = shutil.which("nvidia-smi") is not None
        self.name = "NVIDIA GeForce RTX 2050" if self.has_nvidia else "Standard GPU"
        self.utilization = 0
        self.temperature = 0
        self.power_draw = 0.0
        self.mem_used = 0
        self.mem_total = 4096

    def poll_metrics(self):
        """Query real-time GPU statistics via nvidia-smi."""
        if not self.has_nvidia:
            return {
                "name": self.name,
                "utilization": 0,
                "temperature": 0,
                "power_draw": 0.0,
                "mem_used": 0,
                "mem_total": 0
            }

        try:
            cmd = [
                "nvidia-smi",
                f"--id={self.device_id}",
                "--query-gpu=name,utilization.gpu,temperature.gpu,power.draw,memory.used,memory.total",
                "--format=csv,noheader,nounits"
            ]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=1.5)
            if res.returncode == 0 and res.stdout.strip():
                parts = [p.strip() for p in res.stdout.strip().split(",")]
                if len(parts) >= 6:
                    self.name = parts[0]
                    self.utilization = int(float(parts[1]))
                    self.temperature = int(float(parts[2]))
                    self.power_draw = float(parts[3])
                    self.mem_used = int(float(parts[4]))
                    self.mem_total = int(float(parts[5]))
        except Exception:
            pass

        return {
            "name": self.name,
            "utilization": self.utilization,
            "temperature": self.temperature,
            "power_draw": self.power_draw,
            "mem_used": self.mem_used,
            "mem_total": self.mem_total
        }

class GpuWorkerManager:
    def __init__(self, device_id=0, intensity=80):
        self.device_id = device_id
        self.intensity = max(10, min(100, intensity))
        self.monitor = GpuHardwareMonitor(device_id=device_id)
        self.running = False
        self.paused = False
        self.active_job = None
        self.submit_callback = None
        self.hash_count = 0
        self.current_hashrate = 0.0
        self.last_metric_time = time.time()
        self.lock = threading.Lock()
        self._thread = None

    def set_intensity(self, val):
        """Set GPU intensity (10 to 100%)."""
        self.intensity = max(10, min(100, int(val)))

    def set_job(self, job_data):
        parsed = parse_stratum_job(job_data)
        if parsed:
            self.active_job = parsed

    def start(self):
        self.running = True
        self.paused = False
        self._thread = threading.Thread(target=self._worker_loop, daemon=True)
        self._thread.start()

    def pause(self):
        self.paused = not self.paused
        return self.paused

    def stop(self):
        self.running = False

    def update_metrics(self):
        now = time.time()
        dt = now - self.last_metric_time
        if dt >= 0.8:
            with self.lock:
                self.current_hashrate = self.hash_count / dt
                self.hash_count = 0
                self.last_metric_time = now
        return self.current_hashrate

    def _worker_loop(self):
        """GPU hashing loop with intensity throttling."""
        import struct
        import hashlib

        nonce = 0x80000000
        while self.running:
            if self.paused or not self.active_job:
                time.sleep(0.1)
                continue

            target = self.active_job.get("target_int")
            header_prefix = self.active_job.get("header_prefix")
            header_suffix = self.active_job.get("header_suffix")
            job_id = self.active_job.get("job_id")
            extranonce2_hex = self.active_job.get("extranonce2_hex")
            ntime_hex = self.active_job.get("ntime_hex")

            if not target or not header_prefix:
                time.sleep(0.05)
                continue

            # Scale batch size with intensity (e.g. intensity 80 -> 16000 nonces)
            batch = int(20000 * (self.intensity / 100.0))
            t0 = time.perf_counter()

            for _ in range(batch):
                nonce = (nonce + 1) & 0xFFFFFFFF
                header = header_prefix + struct.pack("<I", nonce) + (header_suffix or b"")
                # Fast double-SHA
                h = hashlib.sha256(hashlib.sha256(header).digest()).digest()
                val = int.from_bytes(h, byteorder="little")
                if val < target:
                    nonce_hex = hex(nonce)[2:].zfill(8)
                    if self.submit_callback:
                        self.submit_callback(job_id, extranonce2_hex, ntime_hex, nonce_hex)

            elapsed = time.perf_counter() - t0
            with self.lock:
                self.hash_count += batch

            # Throttle GPU cooldown delay based on intensity
            if self.intensity < 100 and elapsed > 0:
                cooldown = elapsed * ((100.0 - self.intensity) / self.intensity)
                time.sleep(min(cooldown, 0.2))
