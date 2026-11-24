# ⚡ Crypto Pool Miner & Hardware Usage Controller

An interactive Python + Batch crypto mining controller with Stratum pool connectivity and fine-grained CPU / GPU hardware usage regulation.

---

## 🚀 Quick Start

1. Simply double-click **`run_miner.bat`** in this folder.
2. The interactive controller will open in your terminal.
3. Press **`[1]`** (or hit **ENTER**) to start mining immediately!

---

## 🎛️ Controlling Hardware Usage (CPU & GPU)

You have complete control over how much of your computer's resources are used:

### 1. Device Selection (CPU / GPU / Both)
- Press **`[2]`** in the menu to toggle between **CPU only**, **GPU only**, or **Both (CPU + GPU)**.

### 2. CPU Controls
- **Thread Count (`1` to `12` Cores):** Restrict mining to specific cores. For example, setting 4 threads leaves the remaining 8 cores completely free for gaming, browsing, or office work.
- **Duty Cycle Throttling (`10%` to `100%`):** Controls the work-to-sleep ratio per second. For example, 50% duty cycle runs computing bursts and brief sleeps to keep CPU temperatures low and fans quiet.
- **Process Priority:** Set Windows process priority to `BELOW_NORMAL` or `IDLE`. This ensures Windows automatically prioritizes your web browser, video player, and games ahead of mining.

### 3. GPU Controls
- **GPU Intensity (`10%` to `100%`):** Throttles GPU compute batch sizes and cooldown intervals to prevent thermal throttling or display lag on your NVIDIA GeForce RTX 2050.
- **Hardware Telemetry:** Real-time monitoring of GPU temperature (°C), wattage draw, and load percentage.

---

## ⌨️ Live Runtime Hotkeys (While Mining)

You don't need to restart the miner to change hardware settings! Use these keys directly in the terminal while mining is active:

| Key | Action |
|-----|--------|
| **`+`** | Add 1 active CPU thread on the fly |
| **`-`** | Remove 1 CPU thread on the fly |
| **`t`** | Cycle CPU throttle percentage (`50%` ➔ `75%` ➔ `100%`) |
| **`p`** | Pause / Resume mining instantly |
| **`q`** | Stop mining and return to the main menu |

---

## 🌐 Connecting to a Real Crypto Pool

1. In the main menu, press **`[5]`** (*Configure Target Pool & Wallet*).
2. Enter:
   - **Pool Host:** e.g., `solo.ckpool.org` or `pool.supportxmr.com`
   - **Port:** e.g., `3333`
   - **Wallet Address:** Your public crypto wallet address
   - **Worker Name:** e.g., `rig1`
   - **SSL/TLS:** `y` or `n`
3. Your settings are automatically saved in `config.json` and persist across restarts.

---

## 🧪 Built-in Offline Test Pool

Want to test your CPU/GPU throttling, fans, and share submissions immediately without signing up for a pool?
- Press **`[6]`** (*Run Built-in Test Pool*).
- An offline Stratum simulation server will automatically start on `127.0.0.1:3333`.
- You will see live hashrates, jobs received, and accepted shares right on your screen!

---

## ⚙️ External Production Engines (XMRig / lolMiner)

If you wish to mine production coins (like Monero on CPU or Ravencoin/Kaspa on GPU):
- Press **`[7]`** in the menu to automatically generate the optimized command lines for **XMRig** and **lolMiner** with your exact CPU thread limits (`-t <cores>`), CPU priority (`--cpu-priority`), and GPU intensity flags applied.
