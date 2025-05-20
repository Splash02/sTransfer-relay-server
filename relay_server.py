import socket
import threading
import queue
import time

HOST = '0.0.0.0'
PORT = 5001
DISCONNECT_MSG = b"__DISCONNECT__"
BUFFER_SIZE = 4096

waiting_clients = queue.Queue()
active_pairs = []
lock = threading.Lock()

def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}")

def handle_client(conn, addr):
    log(f"[+] Client connected: {addr}")
    waiting_clients.put((conn, addr))

def relay_data(src, dst, src_addr, dst_addr):
    try:
        while True:
            data = src.recv(BUFFER_SIZE)
            if not data:
                break
            if data.startswith(DISCONNECT_MSG):
                log(f"[!] {src_addr} sent disconnect")
                break
            dst.sendall(data)
    except Exception as e:
        log(f"[!] Relay error {src_addr} -> {dst_addr}: {e}")
    finally:
        cleanup_pair(src, dst, src_addr, dst_addr)

def cleanup_pair(sock1, sock2, addr1, addr2):
    try: sock1.close()
    except: pass
    try: sock2.close()
    except: pass
    with lock:
        active_pairs[:] = [pair for pair in active_pairs if addr1 not in pair and addr2 not in pair]
    log(f"[-] Disconnected: {addr1} & {addr2}")

def match_clients():
    while True:
        conn1, addr1 = waiting_clients.get()
        conn2, addr2 = waiting_clients.get()

        log(f"[=] Pairing {addr1} <-> {addr2}")
        with lock:
            active_pairs.append((addr1, addr2))

        threading.Thread(target=relay_data, args=(conn1, conn2, addr1, addr2), daemon=True).start()
        threading.Thread(target=relay_data, args=(conn2, conn1, addr2, addr1), daemon=True).start()

def main():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((HOST, PORT))
    server.listen(10)
    log(f"[✓] Relay server listening on {HOST}:{PORT}")

    threading.Thread(target=match_clients, daemon=True).start()

    while True:
        conn, addr = server.accept()
        threading.Thread(target=handle_client, args=(conn, addr), daemon=True).start()

if __name__ == "__main__":
    main()
