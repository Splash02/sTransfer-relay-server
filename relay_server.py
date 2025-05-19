import socket
import threading
import os
import queue
import time

HOST = '0.0.0.0'
PORT = int(os.environ.get("PORT", 5001))

waiting_clients = queue.Queue()
active_pairs = []
active_pairs_lock = threading.Lock()

def log(message):
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}")

def relay(src, dst, src_addr, dst_addr):
    try:
        try:
            src.settimeout(1.0)  # Setze Timeout, um saubere Unterbrechung zu ermöglichen
        except OSError:
            log(f"[!] Cannot set timeout on closed socket from {src_addr}")
            return

        while True:
            try:
                data = src.recv(4096)
                if not data:
                    log(f"[*] Connection closed by {src_addr}")
                    break
                try:
                    dst.sendall(data)
                except (BrokenPipeError, OSError) as e:
                    log(f"[!] Failed to send to {dst_addr}: {e}")
                    break
            except socket.timeout:
                continue
            except Exception as e:
                log(f"[!] Relay error from {src_addr} to {dst_addr}: {e}")
                break
    finally:
        # Schließe beide Sockets
        for s in [src, dst]:
            try:
                s.shutdown(socket.SHUT_RDWR)
            except:
                pass
            try:
                s.close()
            except:
                pass

        # Entferne das Paar aus active_pairs
        with active_pairs_lock:
            to_remove = None
            for pair in active_pairs:
                conns = (pair[0][0], pair[1][0])
                addrs = (pair[0][1], pair[1][1])
                if src_addr in addrs or dst_addr in addrs or src in conns or dst in conns:
                    to_remove = pair
                    break
            if to_remove:
                active_pairs.remove(to_remove)

        log(f"[*] Relay connection between {src_addr} and {dst_addr} closed")

def pair_clients():
    while True:
        client1 = waiting_clients.get()
        client2 = waiting_clients.get()
        with active_pairs_lock:
            active_pairs.append((client1, client2))
        log(f"[*] Pairing clients {client1[1]} <--> {client2[1]}")

        threading.Thread(target=relay, args=(client1[0], client2[0], client1[1], client2[1]), daemon=True).start()
        threading.Thread(target=relay, args=(client2[0], client1[0], client2[1], client1[1]), daemon=True).start()

def handle_client(conn, addr):
    log(f"[+] New client connected from {addr}")
    waiting_clients.put((conn, addr))
    log(f"[*] Client {addr} is waiting for a partner...")

def main():
    threading.Thread(target=pair_clients, daemon=True).start()
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((HOST, PORT))
        server.listen()
        log(f"[+] Relay server listening on {HOST}:{PORT}")
        while True:
            try:
                conn, addr = server.accept()
                threading.Thread(target=handle_client, args=(conn, addr), daemon=True).start()
            except Exception as e:
                log(f"[!] Error accepting connection: {e}")

if __name__ == "__main__":
    main()
