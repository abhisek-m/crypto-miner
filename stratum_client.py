"""
Stratum Mining Protocol Client (v1 JSON-RPC over TCP)
Handles connection to standard cryptocurrency mining pools.
"""

import socket
import ssl
import json
import threading
import time

class StratumClient:
    def __init__(self, host, port, wallet, worker_name="worker1", password="x", use_ssl=False):
        self.host = host
        self.port = int(port)
        self.wallet = wallet
        self.worker_name = worker_name
        self.password = password
        self.use_ssl = use_ssl

        self.sock = None
        self.connected = False
        self.authorized = False
        self.running = False

        self.extranonce1 = ""
        self.extranonce2_size = 4
        self.difficulty = 1.0

        self.msg_id = 1
        self.pending_submits = {}  # msg_id -> submit_details

        self.shares_accepted = 0
        self.shares_rejected = 0

        # Callbacks
        self.on_new_job = None
        self.on_share_result = None
        self.on_difficulty_change = None
        self.on_status_change = None

        self._read_thread = None

    def _log_status(self, text):
        if self.on_status_change:
            self.on_status_change(text)

    def connect(self):
        self._log_status(f"Connecting to {self.host}:{self.port}...")
        try:
            raw_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            raw_sock.settimeout(10.0)
            if self.use_ssl:
                context = ssl.create_default_context()
                self.sock = context.wrap_socket(raw_sock, server_hostname=self.host)
            else:
                self.sock = raw_sock

            self.sock.connect((self.host, self.port))
            self.sock.settimeout(1.0)
            self.connected = True
            self.running = True
            self._log_status(f"Connected to {self.host}:{self.port}")

            # Start reading thread
            self._read_thread = threading.Thread(target=self._recv_loop, daemon=True)
            self._read_thread.start()

            # Step 1: Subscribe
            self._send_subscribe()
            return True
        except Exception as e:
            self.connected = False
            self._log_status(f"Connection failed: {e}")
            return False

    def disconnect(self):
        self.running = False
        self.connected = False
        self.authorized = False
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass
        self._log_status("Disconnected from pool.")

    def _send_json(self, method, params, req_id=None):
        if not self.connected or not self.sock:
            return
        if req_id is None:
            req_id = self.msg_id
            self.msg_id += 1

        payload = {"id": req_id, "method": method, "params": params}
        raw = json.dumps(payload) + "\n"
        try:
            self.sock.sendall(raw.encode("utf-8"))
        except Exception as e:
            self._log_status(f"Socket send error: {e}")
            self.connected = False

    def _send_subscribe(self):
        self._send_json("mining.subscribe", ["PyStratumMiner/1.0"], req_id=1)

    def _send_authorize(self):
        user = f"{self.wallet}.{self.worker_name}" if self.worker_name else self.wallet
        self._log_status(f"Authorizing as: {user}")
        self._send_json("mining.authorize", [user, self.password], req_id=2)

    def submit_share(self, job_id, extranonce2, ntime, nonce):
        user = f"{self.wallet}.{self.worker_name}" if self.worker_name else self.wallet
        sub_id = self.msg_id
        self.msg_id += 1
        self.pending_submits[sub_id] = {
            "job_id": job_id,
            "nonce": nonce,
            "timestamp": time.time()
        }
        self._send_json("mining.submit", [user, job_id, extranonce2, ntime, nonce], req_id=sub_id)

    def _recv_loop(self):
        buffer = ""
        while self.running:
            try:
                data = self.sock.recv(4096)
                if not data:
                    self._log_status("Pool closed the connection.")
                    self.connected = False
                    break
                buffer += data.decode("utf-8", errors="ignore")
            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    self._log_status(f"Connection error: {e}")
                self.connected = False
                break

            while "\n" in buffer:
                line, buffer = buffer.split("\n", 1)
                line = line.strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line)
                    self._handle_message(msg)
                except json.JSONDecodeError:
                    continue

    def _handle_message(self, msg):
        msg_id = msg.get("id")
        method = msg.get("method")
        result = msg.get("result")
        error = msg.get("error")

        # Response to subscribe
        if msg_id == 1:
            if error:
                self._log_status(f"Subscribe failed: {error}")
            elif result:
                try:
                    if len(result) >= 3:
                        self.extranonce1 = result[1]
                        self.extranonce2_size = int(result[2])
                    elif len(result) >= 2 and isinstance(result[1], str):
                        self.extranonce1 = result[1]
                except Exception:
                    pass
                self._log_status(f"Subscribed (Extranonce1: {self.extranonce1})")
                self._send_authorize()

        # Response to authorize
        elif msg_id == 2:
            if result is True:
                self.authorized = True
                self._log_status("Authorization SUCCESS! Ready for pool jobs.")
            else:
                self.authorized = False
                self._log_status(f"Authorization FAILED: {error}")

        # Response to submit
        elif msg_id in self.pending_submits:
            submit_info = self.pending_submits.pop(msg_id)
            if result is True:
                self.shares_accepted += 1
                if self.on_share_result:
                    self.on_share_result(True, None, submit_info)
            else:
                self.shares_rejected += 1
                reason = error[1] if isinstance(error, list) and len(error) > 1 else str(error)
                if self.on_share_result:
                    self.on_share_result(False, reason, submit_info)

        # Pool notifications (id is null)
        elif method == "mining.set_difficulty":
            params = msg.get("params", [])
            if params:
                self.difficulty = float(params[0])
                if self.on_difficulty_change:
                    self.on_difficulty_change(self.difficulty)

        elif method == "mining.notify":
            params = msg.get("params", [])
            if params and len(params) >= 9:
                job_data = {
                    "job_id": params[0],
                    "prevhash": params[1],
                    "coinb1": params[2],
                    "coinb2": params[3],
                    "merkle_branch": params[4],
                    "version": params[5],
                    "nbits": params[6],
                    "ntime": params[7],
                    "clean_jobs": params[8],
                    "extranonce1": self.extranonce1,
                    "extranonce2_size": self.extranonce2_size,
                    "difficulty": self.difficulty
                }
                if self.on_new_job:
                    self.on_new_job(job_data)
