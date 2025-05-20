import socket
import threading
import os
import time
import queue

HOST = '0.0.0.0'
PORT = int(os.environ.get("PORT", 5001))

DISCONNECT_MSG = b"__DISCONNECT__"

waiting_clients = queue.Queue()
waiting_clients_lock = threading.Lock()
waiting_clients_set = set()
active_pairs = []

def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}")

def close_socket(sock):
    try: sock.shutdown(socket.SHUT_RDWR)
    except: pass
    try: sock.close()
    except: pass

def relay(src, dst, src_addr, dst_addr):
    try:
        while True:
            data = src.recv(4096)
            if not data or data.startswith(DISCONNECT_MSG):
                break
            dst.sendall(data)
    except:
        pass
    finally:
        close_socket(src)
        close_socket(dst)
        log(f"[x] Closed connection: {src_addr} ↔ {dst_addr}")
        with waiting_clients_lock:
            active_pairs[:] = [pair for pair in active_pairs if src not in pair and dst not in pair]

def pair_clients_loop():
    while True:
        with waiting_clients_lock:
            if waiting_clients.qsize() < 2:
                time.sleep(0.1)
                continue
            try:
                client1, addr1 = waiting_clients.get_nowait()
                client2, addr2 = waiting_clients.get_nowait()
                waiting_clients_set.discard(addr1)
                waiting_clients_set.discard(addr2)
            except queue.Empty:
                continue

        if client1.fileno() == -1 or client2.fileno() == -1:
            log(f"[!] Skipping disconnected client(s): {addr1}, {addr2}")
            close_socket(client1)
            close_socket(client2)
            continue

        with waiting_clients_lock:
            active_pairs.append((client1, client2))

        log(f"[✓] Pairing: {addr1} ↔ {addr2}")
        threading.Thread(target=relay, args=(client1, client2, addr1, addr2), daemon=True).start()
        threading.Thread(target=relay, args=(client2, client1, addr2, addr1), daemon=True).start()

def remove_client(addr, conn):
    with waiting_clients_lock:
        tmp = queue.Queue()
        while not waiting_clients.empty():
            sock, a = waiting_clients.get()
            if a != addr:
                tmp.put((sock, a))
            else:
                close_socket(sock)
                waiting_clients_set.discard(addr)
        while not tmp.empty():
            waiting_clients.put(tmp.get())
    close_socket(conn)

def client_thread(conn, addr):
    log(f"[+] New client: {addr}")
    with waiting_clients_lock:
        if addr not in waiting_clients_set:
            waiting_clients.put((conn, addr))
            waiting_clients_set.add(addr)

    try:
        while True:
            data = conn.recv(4096)
            if not data:
                log(f"[!] {addr} disconnected")
                break
            if data.startswith(DISCONNECT_MSG):
                log(f"[-] {addr} requested disconnect")
                remove_client(addr, conn)
                return
    except Exception as e:
        log(f"[!] Error with {addr}: {e}")
    finally:
        remove_client(addr, conn)

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
