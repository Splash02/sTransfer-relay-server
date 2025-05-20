import socket
import threading
import os
import queue
import time
import struct

HOST = '0.0.0.0'
PORT = int(os.environ.get("PORT", 5001))

waiting_clients = queue.Queue()
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
        try:
            src.shutdown(socket.SHUT_RDWR)
            src.close()
        except:
            pass
        try:
            dst.shutdown(socket.SHUT_RDWR)
            dst.close()
        except:
            pass
        with active_pairs_lock:
            to_remove = None
            for pair in active_pairs:
                conns = (pair[0][0], pair[1][0])
                addrs = (pair[0][1], pair[1][1])
                if src_addr in addrs or dst_addr in addrs:
                    to_remove = pair
                    break
            if to_remove:
                active_pairs.remove(to_remove)
        log(f"[*] Relay connection between {src_addr} and {dst_addr} closed")
def pair_clients():
    while True:
        client1 = waiting_clients.get()
        try:
            client2 = waiting_clients.get(timeout=10)
        except queue.Empty:
            try:
                client1[0].send(b"")
            except:
                try:
                    client1[0].close()
                except:
                    pass
            else:
                waiting_clients.put(client1)
            continue

        dead = False
        for client in (client1, client2):
            try:
                client[0].send(b"")
            except:
                try:
                    client[0].close()
                except:
                    pass
                dead = True

        if dead:
            continue 

        with active_pairs_lock:
            active_pairs.append((client1, client2))
        log(f"[*] Pairing clients {client1[1]} <--> {client2[1]}")

        threading.Thread(target=relay, args=(client1[0], client2[0], client1[1], client2[1]), daemon=True).start()
        threading.Thread(target=relay, args=(client2[0], client1[0], client2[1], client1[1]), daemon=True).start()

def handle_client(conn, addr):
    log(f"[+] New client connected from {addr}")

    conn.settimeout(3.0)
    try:
        peek = conn.recv(4096, socket.MSG_PEEK)
        if peek.startswith(DISCONNECT_MSG):
            conn.recv(len(DISCONNECT_MSG))
            conn.close()
            log(f"[*] Client {addr} disconnected before pairing")
            return
    except socket.timeout:
        pass
    except Exception as e:
        log(f"[!] Error during initial check from {addr}: {e}")
        try:
            conn.close()
        except:
            pass
        return
    
    conn.settimeout(None)

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
