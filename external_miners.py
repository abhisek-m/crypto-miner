"""
External Mining Engine Manager (XMRig / lolMiner / T-Rex)
Maps configured CPU thread limits, CPU priority, and GPU intensity
into optimized command-line arguments for standard mining software.
"""

import os
import shutil
import subprocess

def get_xmrig_command(pool_host, pool_port, wallet, worker_name="rig1", password="x",
                       cpu_threads=4, throttle_pct=75, priority="below_normal"):
    """
    Generate command-line arguments for XMRig (CPU Monero/RandomX).
    Ensures exact thread limit and priority are passed.
    """
    priority_map = {
        "idle": "0",
        "below_normal": "1",
        "normal": "2"
    }
    prio_arg = priority_map.get(priority.lower(), "1")

    cmd = [
        "xmrig.exe",
        "-o", f"{pool_host}:{pool_port}",
        "-u", f"{wallet}.{worker_name}" if worker_name else wallet,
        "-p", password,
        "-t", str(cpu_threads),
        "--cpu-priority", prio_arg,
        "--cpu-max-threads-hint", str(throttle_pct),
        "--donate-level", "1"
    ]
    return cmd

def get_lolminer_command(pool_host, pool_port, wallet, worker_name="rig1",
                         gpu_device_id=0, gpu_intensity=80):
    """
    Generate command-line arguments for lolMiner (GPU Mining).
    """
    cmd = [
        "lolMiner.exe",
        "--pool", f"{pool_host}:{pool_port}",
        "--user", f"{wallet}.{worker_name}" if worker_name else wallet,
        "--devices", str(gpu_device_id),
        "--pci-indexing"
    ]
    return cmd

def detect_available_engines():
    """Detect presence of external miner executables in current dir or PATH."""
    engines = {}
    for name in ["xmrig", "lolminer", "t-rex", "nbminer"]:
        path = shutil.which(name) or shutil.which(f"{name}.exe")
        if not path:
            local_path = os.path.join(os.getcwd(), "miner", "engines", f"{name}.exe")
            if os.path.exists(local_path):
                path = local_path
        if path:
            engines[name] = path
    return engines
