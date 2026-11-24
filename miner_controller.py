"""
Crypto Pool Miner & Hardware Usage Controller
Main application controller providing interactive UI, live telemetry,
and real-time CPU/GPU hardware usage regulation.
"""

import os
import sys
import time
import json
import psutil
import threading

# Add current directory to path
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

from stratum_client import StratumClient
from worker_cpu import CpuWorkerManager
from worker_gpu import GpuWorkerManager, GpuHardwareMonitor
from sim_pool import StratumSimPool
import external_miners

# Optional color formatting
try:
    import colorama
    colorama.init(autoreset=True)
    G = colorama.Fore.GREEN
    C = colorama.Fore.CYAN
    Y = colorama.Fore.YELLOW
    R = colorama.Fore.RED
    M = colorama.Fore.MAGENTA
    W = colorama.Fore.WHITE
    B = colorama.Style.BRIGHT
    RESET = colorama.Style.RESET_ALL
except Exception:
    G = C = Y = R = M = W = B = RESET = ""

CONFIG_PATH = os.path.join(CURRENT_DIR, "config.json")

def load_config():
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "pool": {
            "host": "127.0.0.1",
            "port": 3333,
            "wallet": "bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh",
            "worker_name": "worker1",
            "password": "x",
            "use_ssl": False
        },
        "hardware": {
            "device_mode": "cpu",
            "cpu_threads": 4,
            "cpu_throttle_pct": 75,
            "cpu_priority": "below_normal",
            "gpu_device_id": 0,
            "gpu_intensity": 80
        },
        "options": {
            "show_menu_on_startup": True,
            "auto_start_sim_pool_if_localhost": True
        }
    }

def save_config(cfg):
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
    except Exception as e:
        print(f"[!] Failed to save configuration: {e}")

class MinerControllerApp:
    def __init__(self):
        self.config = load_config()
        self.sim_pool = None
        self.client = None
        self.cpu_worker = None
        self.gpu_worker = None
        self.gpu_monitor = GpuHardwareMonitor(self.config["hardware"].get("gpu_device_id", 0))

        self.status_log = ["Initializing system..."]
        self.running = False
        self.lock = threading.Lock()

    def log_status(self, text):
        with self.lock:
            ts = time.strftime("%H:%M:%S")
            self.status_log.append(f"[{ts}] {text}")
            if len(self.status_log) > 6:
                self.status_log.pop(0)

    def print_banner(self):
        os.system("cls" if os.name == "nt" else "clear")
        print(f"{C}{B}" + "=" * 70)
        print("          CRYPTO POOL MINER & HARDWARE CONTROLLER")
        print("=" * 70 + f"{RESET}")

    def main_menu(self):
        while True:
            self.print_banner()
            pool_cfg = self.config["pool"]
            hw_cfg = self.config["hardware"]

            total_cores = os.cpu_count() or 4
            gpu_info = self.gpu_monitor.poll_metrics()

            print(f"{B}[SYSTEM HARDWARE DETECTED]{RESET}")
            print(f"  CPU Cores:    {G}{total_cores} Logical Cores{RESET}")
            print(f"  GPU Adapter:  {G}{gpu_info['name']}{RESET}")
            print()
            print(f"{B}[CURRENT MINING SETTINGS]{RESET}")
            print(f"  Pool URL:     {C}{pool_cfg['host']}:{pool_cfg['port']}{RESET} (SSL: {pool_cfg.get('use_ssl', False)})")
            print(f"  Wallet/User:  {C}{pool_cfg['wallet']}.{pool_cfg['worker_name']}{RESET}")
            print(f"  Device Mode:  {Y}{hw_cfg['device_mode'].upper()}{RESET} [cpu, gpu, or both]")
            print(f"  CPU Controls: {Y}{hw_cfg['cpu_threads']}/{total_cores} Threads{RESET} | Throttle: {Y}{hw_cfg['cpu_throttle_pct']}%{RESET} | Priority: {Y}{hw_cfg['cpu_priority'].upper()}{RESET}")
            print(f"  GPU Controls: Intensity: {Y}{hw_cfg['gpu_intensity']}%{RESET} (Device ID: {hw_cfg['gpu_device_id']})")
            print("-" * 70)
            print(f"{B}[SELECT ACTION]{RESET}")
            print(f"  {G}[1]{RESET} Start Mining Now (Press Enter)")
            print(f"  {C}[2]{RESET} Toggle Mining Device (CPU / GPU / Both)")
            print(f"  {C}[3]{RESET} Configure CPU Usage (Threads, Throttle %, Priority)")
            print(f"  {C}[4]{RESET} Configure GPU Usage (Intensity %)")
            print(f"  {C}[5]{RESET} Configure Target Pool & Wallet")
            print(f"  {Y}[6]{RESET} Run Built-in Test Pool (Offline Demo / Benchmark)")
            print(f"  {M}[7]{RESET} External Production Miner Integration (XMRig / lolMiner)")
            print(f"  {R}[8]{RESET} Exit")
            print("-" * 70)

            choice = input(f"{B}Enter choice [1-8] or press ENTER to Start: {RESET}").strip()
            if choice == "" or choice == "1":
                self.run_mining_session()
            elif choice == "2":
                self.menu_toggle_device()
            elif choice == "3":
                self.menu_cpu_settings()
            elif choice == "4":
                self.menu_gpu_settings()
            elif choice == "5":
                self.menu_pool_settings()
            elif choice == "6":
                self.menu_sim_pool_test()
            elif choice == "7":
                self.menu_external_miners()
            elif choice == "8":
                print("\nExiting. Happy mining!")
                break

    def menu_toggle_device(self):
        modes = ["cpu", "gpu", "both"]
        current = self.config["hardware"].get("device_mode", "cpu").lower()
        next_idx = (modes.index(current) + 1) % len(modes) if current in modes else 0
        new_mode = modes[next_idx]
        self.config["hardware"]["device_mode"] = new_mode
        save_config(self.config)
        print(f"\n{G}[✓] Device mode switched to: {new_mode.upper()}{RESET}")
        time.sleep(1)

    def menu_cpu_settings(self):
        total_cores = os.cpu_count() or 4
        hw = self.config["hardware"]
        print(f"\n{B}--- CPU USAGE CONFIGURATION ---{RESET}")
        print(f"Total available cores: {total_cores}")

        threads_in = input(f"Enter number of CPU threads [1-{total_cores}] (Current: {hw['cpu_threads']}): ").strip()
        if threads_in.isdigit():
            val = int(threads_in)
            if 1 <= val <= total_cores:
                hw["cpu_threads"] = val

        throttle_in = input(f"Enter CPU Throttle Duty Cycle % [10-100] (Current: {hw['cpu_throttle_pct']}%): ").strip()
        if throttle_in.isdigit():
            val = int(throttle_in)
            if 10 <= val <= 100:
                hw["cpu_throttle_pct"] = val

        print("\nProcess Priority levels: [1] Idle, [2] Below Normal, [3] Normal")
        prio_in = input(f"Select priority (Current: {hw['cpu_priority']}): ").strip()
        if prio_in == "1":
            hw["cpu_priority"] = "idle"
        elif prio_in == "2":
            hw["cpu_priority"] = "below_normal"
        elif prio_in == "3":
            hw["cpu_priority"] = "normal"

        save_config(self.config)
        print(f"{G}[✓] CPU settings updated!{RESET}")
        time.sleep(1.2)

    def menu_gpu_settings(self):
        hw = self.config["hardware"]
        print(f"\n{B}--- GPU USAGE CONFIGURATION ---{RESET}")
        int_in = input(f"Enter GPU Intensity % [10-100] (Current: {hw['gpu_intensity']}%): ").strip()
        if int_in.isdigit():
            val = int(int_in)
            if 10 <= val <= 100:
                hw["gpu_intensity"] = val

        save_config(self.config)
        print(f"{G}[✓] GPU intensity set to {hw['gpu_intensity']}%!{RESET}")
        time.sleep(1)

    def menu_pool_settings(self):
        p = self.config["pool"]
        print(f"\n{B}--- TARGET POOL & WALLET SETTINGS ---{RESET}")
        host_in = input(f"Pool Host/IP (Current: {p['host']}): ").strip()
        if host_in:
            p["host"] = host_in

        port_in = input(f"Pool Port (Current: {p['port']}): ").strip()
        if port_in.isdigit():
            p["port"] = int(port_in)

        wallet_in = input(f"Wallet Address (Current: {p['wallet']}): ").strip()
        if wallet_in:
            p["wallet"] = wallet_in

        worker_in = input(f"Worker Name (Current: {p['worker_name']}): ").strip()
        if worker_in:
            p["worker_name"] = worker_in

        ssl_in = input(f"Use SSL/TLS encryption? (y/n, Current: {p.get('use_ssl', False)}): ").strip().lower()
        if ssl_in in ["y", "yes"]:
            p["use_ssl"] = True
        elif ssl_in in ["n", "no"]:
            p["use_ssl"] = False

        save_config(self.config)
        print(f"{G}[✓] Pool settings saved!{RESET}")
        time.sleep(1.2)

    def menu_sim_pool_test(self):
        print(f"\n{Y}[*] Configuring to run local built-in test pool...{RESET}")
        self.config["pool"]["host"] = "127.0.0.1"
        self.config["pool"]["port"] = 3333
        save_config(self.config)
        print(f"{G}[✓] Pool host set to 127.0.0.1:3333. Starting session now...{RESET}")
        time.sleep(1)
        self.run_mining_session()

    def menu_external_miners(self):
        print(f"\n{B}--- EXTERNAL MINING ENGINE COMMANDS ---{RESET}")
        p = self.config["pool"]
        hw = self.config["hardware"]

        xmrig_cmd = external_miners.get_xmrig_command(
            p["host"], p["port"], p["wallet"], p["worker_name"],
            cpu_threads=hw["cpu_threads"],
            throttle_pct=hw["cpu_throttle_pct"],
            priority=hw["cpu_priority"]
        )
        lol_cmd = external_miners.get_lolminer_command(
            p["host"], p["port"], p["wallet"], p["worker_name"],
            gpu_device_id=hw["gpu_device_id"],
            gpu_intensity=hw["gpu_intensity"]
        )

        print(f"\n{Y}Generated XMRig (CPU RandomX) command with your hardware limits:{RESET}")
        print(f"{C}{' '.join(xmrig_cmd)}{RESET}")

        print(f"\n{Y}Generated lolMiner (GPU) command with your GPU limits:{RESET}")
        print(f"{C}{' '.join(lol_cmd)}{RESET}")

        detected = external_miners.detect_available_engines()
        if detected:
            print(f"\n{G}Found installed engine(s): {list(detected.keys())}{RESET}")
        else:
            print(f"\n{W}Note: Download xmrig.exe or lolMiner.exe into folder if you wish to use them.{RESET}")

        input(f"\nPress Enter to return to main menu...")

    def run_mining_session(self):
        pool_cfg = self.config["pool"]
        hw_cfg = self.config["hardware"]
        self.running = True

        # Check if local test pool needs to be auto-started
        is_localhost = pool_cfg["host"] in ["127.0.0.1", "localhost"]
        if is_localhost and self.config["options"].get("auto_start_sim_pool_if_localhost", True):
            self.sim_pool = StratumSimPool(host="127.0.0.1", port=int(pool_cfg["port"]))
            if self.sim_pool.start():
                self.log_status("Local test pool started on 127.0.0.1:3333")
            time.sleep(0.5)

        # Setup CPU worker
        device_mode = hw_cfg.get("device_mode", "cpu").lower()
        use_cpu = device_mode in ["cpu", "both"]
        use_gpu = device_mode in ["gpu", "both"]

        if use_cpu:
            self.cpu_worker = CpuWorkerManager(
                target_threads=hw_cfg["cpu_threads"],
                throttle_pct=hw_cfg["cpu_throttle_pct"],
                priority=hw_cfg["cpu_priority"]
            )
            self.cpu_worker.start()

        if use_gpu:
            self.gpu_worker = GpuWorkerManager(
                device_id=hw_cfg["gpu_device_id"],
                intensity=hw_cfg["gpu_intensity"]
            )
            self.gpu_worker.start()

        # Setup Stratum Client
        self.client = StratumClient(
            host=pool_cfg["host"],
            port=pool_cfg["port"],
            wallet=pool_cfg["wallet"],
            worker_name=pool_cfg["worker_name"],
            password=pool_cfg.get("password", "x"),
            use_ssl=pool_cfg.get("use_ssl", False)
        )

        def on_job(job_data):
            self.log_status(f"New Job #{job_data['job_id']} (Diff: {job_data.get('difficulty', 1.0)})")
            if self.cpu_worker:
                self.cpu_worker.set_job(job_data)
            if self.gpu_worker:
                self.gpu_worker.set_job(job_data)

        def on_share(accepted, reason, info):
            if accepted:
                self.log_status(f"{G}SHARE ACCEPTED! (Job #{info.get('job_id')}){RESET}")
            else:
                self.log_status(f"{R}Share rejected: {reason}{RESET}")

        def on_diff(diff):
            self.log_status(f"Pool difficulty adjusted to: {diff}")

        def on_status(text):
            self.log_status(text)

        self.client.on_new_job = on_job
        self.client.on_share_result = on_share
        self.client.on_difficulty_change = on_diff
        self.client.on_status_change = on_status

        # Link share submission callback from workers to Stratum client
        def submit_handler(job_id, extranonce2, ntime, nonce):
            self.client.submit_share(job_id, extranonce2, ntime, nonce)

        if self.cpu_worker:
            self.cpu_worker.submit_callback = submit_handler
        if self.gpu_worker:
            self.gpu_worker.submit_callback = submit_handler

        self.client.connect()

        # Keyboard non-blocking input setup for Windows
        has_msvcrt = False
        try:
            import msvcrt
            has_msvcrt = True
        except ImportError:
            pass

        first_draw = True
        try:
            last_render = 0
            while self.running:
                now = time.time()
                if now - last_render >= 1.0:
                    self.render_dashboard(use_cpu, use_gpu, first_draw=first_draw)
                    first_draw = False
                    last_render = now

                # Check interactive keypresses
                if has_msvcrt and msvcrt.kbhit():
                    ch = msvcrt.getch()
                    try:
                        key = ch.decode("utf-8").lower()
                    except Exception:
                        key = ""

                    if key == "q":
                        self.log_status("Stopping mining session...")
                        break
                    elif key == "+" or key == "=":
                        if self.cpu_worker:
                            if self.cpu_worker.add_thread():
                                hw_cfg["cpu_threads"] = self.cpu_worker.target_threads
                                save_config(self.config)
                                self.log_status(f"Added CPU thread: now {self.cpu_worker.target_threads}")
                    elif key == "-":
                        if self.cpu_worker:
                            if self.cpu_worker.remove_thread():
                                hw_cfg["cpu_threads"] = self.cpu_worker.target_threads
                                save_config(self.config)
                                self.log_status(f"Removed CPU thread: now {self.cpu_worker.target_threads}")
                    elif key == "t":
                        # Adjust throttle
                        new_th = (hw_cfg["cpu_throttle_pct"] % 100) + 25
                        if new_th > 100:
                            new_th = 50
                        hw_cfg["cpu_throttle_pct"] = new_th
                        if self.cpu_worker:
                            self.cpu_worker.set_throttle(new_th)
                        save_config(self.config)
                        self.log_status(f"CPU throttle set to {new_th}%")
                    elif key == "p":
                        is_paused = False
                        if self.cpu_worker:
                            is_paused = self.cpu_worker.pause()
                        if self.gpu_worker:
                            is_paused = self.gpu_worker.pause()
                        self.log_status("Mining PAUSED" if is_paused else "Mining RESUMED")

                time.sleep(0.05)
        except KeyboardInterrupt:
            self.log_status("Session interrupted by user.")
        finally:
            self.cleanup_session()

    def render_dashboard(self, use_cpu, use_gpu, first_draw=False):
        hw_cfg = self.config["hardware"]
        pool_cfg = self.config["pool"]
        total_cores = os.cpu_count() or 4

        # Calculate combined hashrate
        cpu_hr = self.cpu_worker.update_metrics() if self.cpu_worker else 0.0
        gpu_hr = self.gpu_worker.update_metrics() if self.gpu_worker else 0.0
        total_hr = cpu_hr + gpu_hr

        # Format hashrate string
        if total_hr >= 1_000_000:
            hr_str = f"{total_hr / 1_000_000:.2f} MH/s"
        elif total_hr >= 1_000:
            hr_str = f"{total_hr / 1_000:.2f} kH/s"
        else:
            hr_str = f"{total_hr:.1f} H/s"

        # Hardware metrics
        overall_cpu_pct = psutil.cpu_percent()
        gpu_metrics = self.gpu_monitor.poll_metrics()

        conn_status = f"{G}CONNECTED & MINING{RESET}" if self.client and self.client.connected else f"{R}CONNECTING / WAITING{RESET}"

        total_shares = (self.client.shares_accepted + self.client.shares_rejected) if self.client else 0
        ratio = (self.client.shares_accepted / total_shares * 100) if total_shares > 0 else 100.0

        # Build dashboard lines
        lines = []
        lines.append(f"{C}{B}" + "=" * 70 + f"{RESET}")
        lines.append(f"{C}{B}                   MINING IN PROGRESS{RESET}")
        lines.append(f"{C}{B}" + "=" * 70 + f"{RESET}")
        lines.append(f" Pool:        {pool_cfg['host']}:{pool_cfg['port']}  [{conn_status}]")
        lines.append(f" Account:     {pool_cfg['wallet']}.{pool_cfg['worker_name']}")
        lines.append(f" Hashrate:    {G}{B}{hr_str}{RESET} (Combined speed)")
        lines.append(f" Shares:      {G}Accepted: {self.client.shares_accepted if self.client else 0}{RESET}  |  "
                     f"{R}Rejected: {self.client.shares_rejected if self.client else 0}{RESET}  "
                     f"(Success: {ratio:.1f}%)")
        lines.append("-" * 70)
        lines.append(f"{B}[HARDWARE CONTROLS & DEVICE STATUS]{RESET}")

        if use_cpu:
            cpu_th = self.cpu_worker.target_threads if self.cpu_worker else hw_cfg["cpu_threads"]
            duty = self.cpu_worker.throttle_pct if self.cpu_worker else hw_cfg["cpu_throttle_pct"]
            prio = hw_cfg["cpu_priority"].upper()
            lines.append(f"  CPU Device:  {G}ACTIVE{RESET} -> {cpu_th} of {total_cores} Cores in use ({int(cpu_th/total_cores*100)}% allocated)")
            lines.append(f"               Duty Cycle / Throttle: {Y}{duty}%{RESET} | Process Priority: {Y}{prio}{RESET}")
            lines.append(f"               Real-time System CPU Load: {overall_cpu_pct}%")
        else:
            lines.append(f"  CPU Device:  {W}Disabled (Standby){RESET}")

        if use_gpu:
            intensity = self.gpu_worker.intensity if self.gpu_worker else hw_cfg["gpu_intensity"]
            temp = gpu_metrics["temperature"]
            power = gpu_metrics["power_draw"]
            gpu_u = gpu_metrics["utilization"]
            lines.append(f"  GPU Device:  {G}ACTIVE{RESET} -> {gpu_metrics['name']} (Intensity: {intensity}%)")
            lines.append(f"               Temp: {temp} C | Power: {power}W | GPU Load: {gpu_u}%")
        else:
            lines.append(f"  GPU Device:  {W}Disabled (Standby){RESET}")

        lines.append("-" * 70)
        lines.append(f"{B}[POOL EVENTS & ACTIVITY]{RESET}")
        for log in self.status_log[-5:]:
            lines.append(f"  {log}")

        lines.append("-" * 70)
        lines.append(f"{B}[LIVE KEYBOARD CONTROLS]{RESET}")
        lines.append(f"  {Y}[+]{RESET} Add CPU Core   {Y}[-]{RESET} Remove CPU Core   {Y}[t]{RESET} Cycle Throttle (50/75/100%)")
        lines.append(f"  {Y}[p]{RESET} Pause/Resume   {R}[q]{RESET} Stop Mining & Return to Menu")
        lines.append("=" * 70)

        # Zero-flicker render:
        # If first draw, clear screen once and hide cursor
        # If subsequent draw, move cursor to (0,0) and overwrite buffer in-place
        if first_draw:
            os.system("cls" if os.name == "nt" else "clear")
            sys.stdout.write("\033[?25l")  # Hide cursor to prevent flicker
        else:
            sys.stdout.write("\033[H")     # Move cursor home (0,0)

        # Output with \033[K (clear to end of line) on each row
        buffer = "\n".join(line + "\033[K" for line in lines) + "\n"
        sys.stdout.write(buffer)
        sys.stdout.flush()

    def cleanup_session(self):
        self.running = False
        sys.stdout.write("\033[?25h")  # Restore cursor
        sys.stdout.flush()
        if self.client:
            self.client.disconnect()
        if self.cpu_worker:
            self.cpu_worker.stop()
        if self.gpu_worker:
            self.gpu_worker.stop()
        if self.sim_pool:
            self.sim_pool.stop()
        print("\nSession stopped. Cleaned up all resources.")
        time.sleep(1)

if __name__ == "__main__":
    app = MinerControllerApp()
    # Check if started directly with --start flag or open menu
    if len(sys.argv) > 1 and sys.argv[1] == "--start":
        app.run_mining_session()
    else:
        app.main_menu()
