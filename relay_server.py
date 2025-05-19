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

def is_socket_closed(sock):
    try:
        sock.setblocking(0)
        data = sock.recv(1, socket.MSG_PEEK)
        return not data
    except BlockingIOError:
        return False
    except OSError:
        return True
    finally:
        sock.setblocking(1)

def relay(src, dst, src_addr, dst_addr):
    try:
        src.settimeout(1.0)  # Timeout setzen, damit recv nicht ewig blockiert
        while True:
            try:
                data = src.recv(4096)
                if not data:
                    log(f"[*] Connection closed by {src_addr}")
                    break
                dst.sendall(data)
            except socket.timeout:
                continue  # Timeout bedeutet: weiter warten
            except OSError as e:
                log(f"[!] OSError in relay from {src_addr} to {dst_addr}: {e}")
                break
    except Exception as e:
        log(f"[!] Relay error between {src_addr} and {dst_addr}: {e}")
    finally:
        for s in (src, dst):
            try:
                s.shutdown(socket.SHUT_RDWR)
                s.close()
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
        client1 = None
        client2 = None

        # Erstes gültiges Paar finden
        while not client1:
            potential = waiting_clients.get()
            if not is_socket_closed(potential[0]):
                client1 = potential
            else:
                log(f"[*] Ignored closed socket {potential[1]} (client1)")

        while not client2:
            potential = waiting_clients.get()
            if not is_socket_closed(potential[0]):
                client2 = potential
            else:
                log(f"[*] Ignored closed socket {potential[1]} (client2)")

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
