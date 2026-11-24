"""
Simulated Stratum Mining Pool Server for local testing and benchmarking.
Emulates Stratum v1 protocol JSON-RPC over TCP.
"""

import socket
import threading
import json
import time
import uuid
import hashlib
import os

class StratumSimPool:
    def __init__(self, host="127.0.0.1", port=3333, difficulty=0.00005):
        self.host = host
        self.port = port
        self.difficulty = difficulty
        self.running = False
        self.server_socket = None
        self.clients = []
        self.thread = None
        self.current_job_id = 1
        self.shares_accepted = 0
        self.shares_rejected = 0

    def start(self):
        self.running = True
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            self.server_socket.bind((self.host, self.port))
            self.server_socket.listen(5)
            self.server_socket.settimeout(1.0)
        except Exception as e:
            print(f"[Sim Pool] Failed to bind to {self.host}:{self.port}: {e}")
            self.running = False
            return False

        self.thread = threading.Thread(target=self._accept_loop, daemon=True)
        self.thread.start()
        return True

    def stop(self):
        self.running = False
        if self.server_socket:
            try:
                self.server_socket.close()
            except Exception:
                pass
        for client in self.clients:
            try:
                client.close()
            except Exception:
                pass
        self.clients.clear()

    def _accept_loop(self):
        while self.running:
            try:
                client_sock, addr = self.server_socket.accept()
                self.clients.append(client_sock)
                t = threading.Thread(target=self._client_handler, args=(client_sock, addr), daemon=True)
                t.start()
            except socket.timeout:
                continue
            except Exception:
                break

    def _client_handler(self, sock, addr):
        buffer = ""
        extranonce1 = "01020304"
        extranonce2_size = 4
        authorized = False
        worker_name = "unknown"

        try:
            sock.settimeout(1.0)
            while self.running:
                try:
                    data = sock.recv(4096)
                    if not data:
                        break
                    buffer += data.decode("utf-8", errors="ignore")
                except socket.timeout:
                    continue

                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        req = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    msg_id = req.get("id")
                    method = req.get("method")
                    params = req.get("params", [])

                    if method == "mining.subscribe":
                        resp = {
                            "id": msg_id,
                            "result": [
                                [
                                    ["mining.set_difficulty", "b4b6693b72a50c7116db18d6497cac52"],
                                    ["mining.notify", "ae6812eb4cd7735a302a8a9dd95cf71f"]
                                ],
                                extranonce1,
                                extranonce2_size
                            ],
                            "error": None
                        }
                        self._send(sock, resp)

                        # Send initial difficulty
                        diff_notif = {
                            "id": None,
                            "method": "mining.set_difficulty",
                            "params": [self.difficulty]
                        }
                        self._send(sock, diff_notif)

                    elif method == "mining.authorize":
                        worker_name = params[0] if len(params) > 0 else "worker"
                        authorized = True
                        resp = {"id": msg_id, "result": True, "error": None}
                        self._send(sock, resp)

                        # Send first job
                        self._send_job(sock)

                    elif method == "mining.submit":
                        self.shares_accepted += 1
                        resp = {"id": msg_id, "result": True, "error": None}
                        self._send(sock, resp)

            # Cleanup
            if sock in self.clients:
                self.clients.remove(sock)
            sock.close()
        except Exception:
            if sock in self.clients:
                self.clients.remove(sock)
            try:
                sock.close()
            except Exception:
                pass

    def _send(self, sock, data_dict):
        try:
            msg = json.dumps(data_dict) + "\n"
            sock.sendall(msg.encode("utf-8"))
        except Exception:
            pass

    def _send_job(self, sock):
        job_id = hex(self.current_job_id)[2:]
        self.current_job_id += 1

        prevhash = "00000000000000000005a76f2d8a4f4943f65d6428c9b3d0ee2a933ff444391e"
        coinb1 = "01000000010000000000000000000000000000000000000000000000000000000000000000ffffffff2002522b072f503253482f"
        coinb2 = "000000000000"
        merkle_branch = [
            "2002522b072f503253482f0000000000000000000000000000000000000000",
            "43f65d6428c9b3d0ee2a933ff444391e00000000000000000000000000000000"
        ]
        version = "20000000"
        nbits = "1d00ffff"
        ntime = hex(int(time.time()))[2:].zfill(8)
        clean_jobs = True

        notif = {
            "id": None,
            "method": "mining.notify",
            "params": [
                job_id,
                prevhash,
                coinb1,
                coinb2,
                merkle_branch,
                version,
                nbits,
                ntime,
                clean_jobs
            ]
        }
        self._send(sock, notif)

if __name__ == "__main__":
    pool = StratumSimPool()
    if pool.start():
        print("Test pool running on 127.0.0.1:3333. Press Ctrl+C to stop.")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pool.stop()
