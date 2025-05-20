import socket
import threading
import os
import queue
import time

HOST = '0.0.0.0'
PORT = int(os.environ.get("PORT", 5001))

waiting_clients = queue.Queue()
waiting_clients_list = [] 
active_pairs = []
active_pairs_lock = threading.Lock()

DISCONNECT_MSG = b"__DISCONNECT__"

def log(message):
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}")

def relay(src, dst, src_addr, dst_addr):
    try:
        while True:
            data = src.recv(4096)
            if not data or data.startswith(DISCONNECT_MSG):
                log(f"[*] {src_addr} disconnected")
                break
            dst.sendall(data)
    except Exception as e:
        log(f"[!] Relay error between {src_addr} and {dst_addr}: {e}")
    finally:
        for conn in (src, dst):
            try: conn.shutdown(socket.SHUT_RDWR)
            except: pass
            try: conn.close()
            except: pass

        with active_pairs_lock:
            active_pairs[:] = [pair for pair in active_pairs if src not in pair and dst not in pair]

        log(f"[*] Relay between {src_addr} and {dst_addr} closed")

def pair_clients():
    while True:
        client1, addr1 = waiting_clients.get()
        client2, addr2 = waiting_clients.get()

        # Check if clients are still connected
        if client1.fileno() == -1 or client2.fileno() == -1:
            log(f"[!] One of the clients disconnected before pairing. Skipping.")
            continue

        with active_pairs_lock:
            active_pairs.append((client1, client2))

        log(f"[*] Pairing clients {addr1} <--> {addr2}")
        threading.Thread(target=relay, args=(client1, client2, addr1, addr2), daemon=True).start()
        threading.Thread(target=relay, args=(client2, client1, addr2, addr1), daemon=True).start()

def handle_client(conn, addr):
    log(f"[+] Client connected from {addr}")
    waiting_clients_list.append((conn, addr))
    waiting_clients.put((conn, addr))
    log(f"[*] Client {addr} added to waiting queue")

    try:
        while True:
            data = conn.recv(4096)
            if not data:
                log(f"[!] Client {addr} disconnected unexpectedly")
                break
            if data.startswith(DISCONNECT_MSG):
                log(f"[*] Client {addr} sent DISCONNECT")

                # Remove from queue if still waiting
                removed = False
                with waiting_clients.mutex:
                    for i, (c, a) in enumerate(list(waiting_clients.queue)):
                        if a == addr:
                            del waiting_clients.queue[i]
                            removed = True
                            break

                # Remove from list
                for i, (c, a) in enumerate(waiting_clients_list):
                    if a == addr:
                        try: c.close()
                        except: pass
                        del waiting_clients_list[i]
                        break

                if removed:
                    log(f"[*] Client {addr} removed from waiting queue")
                break
    except:
        pass
    finally:
        try: conn.close()
        except: pass

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
