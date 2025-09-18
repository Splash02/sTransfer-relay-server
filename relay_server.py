import socket
import threading
import time

HOST = "0.0.0.0"
PORT = 5001
BUFFER_SIZE = 4096
DISCONNECT_MSG = b"__DISCONNECT__"

lock = threading.Lock()
waiting_clients = []  # Liste aller wartenden Clients

def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}")

class Client:
    def __init__(self, conn, addr):
        self.conn = conn
        self.addr = addr
        self.partner = None
        self.alive = True

    def close(self):
        self.alive = False
        try:
            self.conn.close()
        except:
            pass

def monitor_waiting():
    """Entfernt automatisch Clients aus waiting, die disconnected sind"""
    global waiting_clients
    while True:
        with lock:
            waiting_clients = [c for c in waiting_clients if c.alive]
        time.sleep(0.2)

def handle_client(conn, addr):
    client = Client(conn, addr)
    try:
        while client.alive:
            line = b""
            while not line.endswith(b"\n"):
                part = conn.recv(1)
                if not part:
                    client.close()
                    break
                line += part
            if not client.alive:
                break

            cmd = line.strip()
            if cmd == b"JOIN":
                log(f"{addr} joined")
                paired = False
                with lock:
                    # Prüfe, ob ein anderer wartender Client existiert
                    for waiting in waiting_clients:
                        if waiting.alive and waiting != client:
                            # Pairing
                            client.partner = waiting
                            waiting.partner = client
                            waiting_clients.remove(waiting)
                            paired = True
                            threading.Thread(target=relay, args=(client, waiting), daemon=True).start()
                            threading.Thread(target=relay, args=(waiting, client), daemon=True).start()
                            log(f"Paired {client.addr} <-> {waiting.addr}")
                            break
                    if not paired:
                        waiting_clients.append(client)
                        log(f"{client.addr} wartet auf Partner...")
            elif cmd == b"LEAVE":
                log(f"{addr} left before pairing")
                client.close()
                with lock:
                    if client in waiting_clients:
                        waiting_clients.remove(client)
                break
            else:
                log(f"{addr} sent unknown command: {cmd}")
                client.close()
                with lock:
                    if client in waiting_clients:
                        waiting_clients.remove(client)
                break
    except Exception as e:
        log(f"Error {addr}: {e}")
    finally:
        client.close()
        with lock:
            if client in waiting_clients:
                waiting_clients.remove(client)

def relay(src: Client, dst: Client):
    """Leitet Daten von src -> dst weiter"""
    try:
        while src.alive and dst.alive:
            try:
                data = src.conn.recv(BUFFER_SIZE)
            except:
                break
            if not data or data == DISCONNECT_MSG:
                break
            try:
                dst.conn.sendall(data)
            except:
                break
    finally:
        log(f"{src.addr} disconnected")
        src.close()
        if dst.alive:
            try:
                dst.conn.sendall(DISCONNECT_MSG)
            except:
                pass
            dst.close()

def main():
    threading.Thread(target=monitor_waiting, daemon=True).start()
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((HOST, PORT))
    srv.listen(50)
    log(f"Relay server listening on {HOST}:{PORT}")

    while True:
        conn, addr = srv.accept()
        threading.Thread(target=handle_client, args=(conn, addr), daemon=True).start()

if __name__ == "__main__":
    main()
