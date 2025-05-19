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

def is_socket_alive(conn):
    try:
        conn.settimeout(0.1)
        data = conn.recv(1, socket.MSG_PEEK)
        conn.settimeout(None)
        return True
    except socket.error:
        return False

def relay(src, dst, src_addr, dst_addr):
    try:
        while True:
            data = src.recv(4096)
            if not data:
                log(f"[*] Connection closed by {src_addr}")
                break
            dst.sendall(data)
    except Exception as e:
        log(f"[!] Relay error between {src_addr} and {dst_addr}: {e}")
    finally:
        for sock in [src, dst]:
            try:
                sock.shutdown(socket.SHUT_RDWR)
                sock.close()
            except:
                pass

        with active_pairs_lock:
            active_pairs[:] = [p for p in active_pairs if src not in (p[0][0], p[1][0]) and dst not in (p[0][0], p[1][0])]

        log(f"[*] Relay connection between {src_addr} and {dst_addr} closed")

def pair_clients():
    while True:
        client1 = waiting_clients.get()
        try:
            # Warte auf zweites Gegenstück
            while True:
                client2 = waiting_clients.get()
                if client1[0] == client2[0]:
                    continue  # nicht sich selbst verbinden
                if is_socket_alive(client1[0]) and is_socket_alive(client2[0]):
                    break  # beide sind bereit
                else:
                    for client in [client1, client2]:
                        try:
                            client[0].close()
                        except:
                            pass
                    client1 = None
                    break

            if client1 is None:
                continue

            with active_pairs_lock:
                active_pairs.append((client1, client2))

            log(f"[*] Pairing clients {client1[1]} <--> {client2[1]}")
            threading.Thread(target=relay, args=(client1[0], client2[0], client1[1], client2[1]), daemon=True).start()
            threading.Thread(target=relay, args=(client2[0], client1[0], client2[1], client1[1]), daemon=True).start()

        except Exception as e:
            log(f"[!] Error during pairing: {e}")

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
