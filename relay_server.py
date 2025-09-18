import socket
import threading
import time

HOST = "0.0.0.0"    # Hört auf allen Interfaces
PORT = 5001
BUFFER_SIZE = 4096
DISCONNECT_MSG = b"__DISCONNECT__"

lock = threading.Lock()
waiting = None  # Ein wartender Client, maximal ein Client in der Warteschlange

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

def handle_client(client: Client):
    global waiting
    conn, addr = client.conn, client.addr
    try:
        while client.alive:
            # Warte auf JOIN oder LEAVE Nachricht
            line = b""
            while not line.endswith(b"\n"):
                part = conn.recv(1)
                if not part:
                    raise ConnectionResetError()
                line += part
            line = line.strip()

            if line == b"JOIN":
                log(f"{addr} joined")
                with lock:
                    if waiting is None:
                        waiting = client
                        log(f"{addr} wartet auf Partner...")
                    else:
                        partner = waiting
                        waiting = None
                        client.partner = partner
                        partner.partner = client
                        # Starte Relay Threads für beide Richtungen
                        threading.Thread(target=relay, args=(client, partner), daemon=True).start()
                        threading.Thread(target=relay, args=(partner, client), daemon=True).start()
                        log(f"Paired {addr} <-> {partner.addr}")
                break

            elif line == b"LEAVE":
                log(f"{addr} left before pairing")
                client.close()
                with lock:
                    if waiting is client:
                        waiting = None
                break

            else:
                log(f"{addr} sent unknown command: {line}")
                client.close()
                break

    except Exception as e:
        log(f"Error {addr}: {e}")
        client.close()
        with lock:
            if waiting is client:
                waiting = None

def relay(src: Client, dst: Client):
    """Leitet Daten von src -> dst weiter, bis Disconnect oder EOF"""
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
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((HOST, PORT))
    srv.listen(50)
    log(f"Relay server listening on {HOST}:{PORT}")

    while True:
        conn, addr = srv.accept()
        client = Client(conn, addr)
        threading.Thread(target=handle_client, args=(client,), daemon=True).start()

if __name__ == "__main__":
    main()
