import socket
import threading
import queue
import time

HOST = '0.0.0.0'
PORT = 5001
DISCONNECT_MSG = b"__DISCONNECT__"

waiting_clients = queue.Queue()
active_pairs = []
active_pairs_lock = threading.Lock()

def log(msg):
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}")

def relay_loop(src, dst, src_addr, dst_addr):
    try:
        while True:
            data = src.recv(4096)
            if not data:
                log(f"[-] {src_addr} disconnected")
                break
            if data.startswith(DISCONNECT_MSG):
                log(f"[*] {src_addr} sent DISCONNECT")
                break
            dst.sendall(data)
    except Exception as e:
        log(f"[!] Relay error {src_addr} → {dst_addr}: {e}")
    finally:
        try: src.close()
        except: pass
        try: dst.close()
        except: pass
        with active_pairs_lock:
            active_pairs[:] = [pair for pair in active_pairs if src not in pair and dst not in pair]
        log(f"[x] Relay {src_addr} ↔ {dst_addr} closed")

def pair_clients():
    while True:
        client1 = waiting_clients.get()
        client2 = waiting_clients.get()
        with active_pairs_lock:
            active_pairs.append((client1[0], client2[0]))
        log(f"[+] Paired {client1[1]} ↔ {client2[1]}")
        threading.Thread(target=relay_loop, args=(client1[0], client2[0], client1[1], client2[1]), daemon=True).start()
        threading.Thread(target=relay_loop, args=(client2[0], client1[0], client2[1], client1[1]), daemon=True).start()

def handle_client(conn, addr):
    log(f"[.] New client from {addr}")
    waiting_clients.put((conn, addr))

def main():
    threading.Thread(target=pair_clients, daemon=True).start()
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((HOST, PORT))
        s.listen()
        log(f"[✅] Relay listening on {HOST}:{PORT}")
        while True:
            try:
                conn, addr = s.accept()
                threading.Thread(target=handle_client, args=(conn, addr), daemon=True).start()
            except Exception as e:
                log(f"[!] Accept error: {e}")

if __name__ == "__main__":
    main()
