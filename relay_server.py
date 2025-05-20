import socket
import threading
import os
import queue
import time
import struct

HOST = '0.0.0.0'
PORT = int(os.environ.get("PORT", 5001))

waiting_clients = queue.Queue()
waiting_clients_list = []  # Extra zum Entfernen einzelner Clients
active_pairs = []
active_pairs_lock = threading.Lock()

DISCONNECT_MSG = b"__DISCONNECT__"

def log(message):
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}")

def relay(src, dst, src_addr, dst_addr):
    try:
        while True:
            data = src.recv(4096)
            if not data:
                log(f"[*] Connection closed by {src_addr}")
                break
            if data.startswith(DISCONNECT_MSG):
                log(f"[*] {src_addr} sent DISCONNECT")
                break
            dst.sendall(data)
    except Exception as e:
        log(f"[!] Relay error between {src_addr} and {dst_addr}: {e}")
    finally:
        try: src.shutdown(socket.SHUT_RDWR)
        except: pass
        try: src.close()
        except: pass
        try: dst.shutdown(socket.SHUT_RDWR)
        except: pass
        try: dst.close()
        except: pass
        with active_pairs_lock:
            to_remove = None
            for pair in active_pairs:
                if src_addr in (pair[0][1], pair[1][1]):
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

def monitor_disconnect(conn, addr):
    try:
        while True:
            data = conn.recv(4096)
            if not data:
                break
            if data.startswith(DISCONNECT_MSG):
                log(f"[*] {addr} actively disconnected")
                # Aus Warteliste entfernen
                try:
                    # Filter queue
                    global waiting_clients
                    new_q = queue.Queue()
                    while not waiting_clients.empty():
                        item = waiting_clients.get()
                        if item[1] != addr:
                            new_q.put(item)
                    waiting_clients = new_q
                except Exception as e:
                    log(f"[!] Failed to clean waiting queue: {e}")

                # Auch aus Liste entfernen
                for i, (sock, a) in enumerate(waiting_clients_list):
                    if a == addr:
                        try: sock.close()
                        except: pass
                        del waiting_clients_list[i]
                        break
                return
    except:
        pass
    finally:
        try: conn.close()
        except: pass

def handle_client(conn, addr):
    log(f"[+] New client connected from {addr}")
    waiting_clients_list.append((conn, addr))
    waiting_clients.put((conn, addr))
    log(f"[*] Client {addr} is waiting for a partner...")
    threading.Thread(target=monitor_disconnect, args=(conn, addr), daemon=True).start()

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
