import socket
import threading
import os
import time
import queue

HOST = '0.0.0.0'
PORT = int(os.environ.get("PORT", 5001))

DISCONNECT_MSG = b"__DISCONNECT__"

waiting_clients = queue.Queue()
waiting_clients_list = []
active_pairs = []
lock = threading.Lock()

def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}")

def handle_relay(client_a, client_b, addr_a, addr_b):
    def forward(src, dst, src_addr, dst_addr):
        try:
            while True:
                data = src.recv(4096)
                if not data or data.startswith(DISCONNECT_MSG):
                    break
                dst.sendall(data)
        except Exception as e:
            log(f"[!] Relay error {src_addr} → {dst_addr}: {e}")
        finally:
            try: src.shutdown(socket.SHUT_RDWR)
            except: pass
            try: src.close()
            except: pass
            try: dst.shutdown(socket.SHUT_RDWR)
            except: pass
            try: dst.close()
            except: pass
            log(f"[x] Connection closed: {src_addr} ↔ {dst_addr}")
            with lock:
                if (client_a, client_b) in active_pairs:
                    active_pairs.remove((client_a, client_b))
                elif (client_b, client_a) in active_pairs:
                    active_pairs.remove((client_b, client_a))

    threading.Thread(target=forward, args=(client_a, client_b, addr_a, addr_b), daemon=True).start()
    threading.Thread(target=forward, args=(client_b, client_a, addr_b, addr_a), daemon=True).start()

def pair_clients_loop():
    while True:
        client1, addr1 = waiting_clients.get()
        client2, addr2 = waiting_clients.get()


        if client1.fileno() == -1 or client2.fileno() == -1:
            log(f"[!] Skipping disconnected client(s): {addr1}, {addr2}")
            for c in (client1, client2):
                try: c.close()
                except: pass
            continue

        with lock:
            active_pairs.append((client1, client2))

        log(f"[+] Pairing: {addr1} ↔ {addr2}")
        handle_relay(client1, client2, addr1, addr2)

def remove_from_waiting(addr):
    with lock:

        tmp = queue.Queue()
        while not waiting_clients.empty():
            c, a = waiting_clients.get()
            if a != addr:
                tmp.put((c, a))
            else:
                try: c.close()
                except: pass
        while not tmp.empty():
            waiting_clients.put(tmp.get())


        for i, (c, a) in enumerate(waiting_clients_list):
            if a == addr:
                try: c.close()
                except: pass
                del waiting_clients_list[i]
                break

def client_thread(conn, addr):
    log(f"[+] New client: {addr}")

    with lock:
        waiting_clients.put((conn, addr))
        waiting_clients_list.append((conn, addr))

    try:
        while True:
            data = conn.recv(4096)
            if not data:
                log(f"[!] {addr} disconnected unexpectedly")
                break
            if data.startswith(DISCONNECT_MSG):
                log(f"[-] {addr} requested disconnect")
                remove_from_waiting(addr)
                break
    except Exception as e:
        log(f"[!] Error with {addr}: {e}")
    finally:
        try: conn.close()
        except: pass

def start_server():
    threading.Thread(target=pair_clients_loop, daemon=True).start()
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((HOST, PORT))
        s.listen()
        log(f"[Server] Listening on {HOST}:{PORT}")
        while True:
            conn, addr = s.accept()
            threading.Thread(target=client_thread, args=(conn, addr), daemon=True).start()

if __name__ == "__main__":
    start_server()
