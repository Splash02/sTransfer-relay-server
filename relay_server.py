import socket
import threading
import time

HOST = "0.0.0.0"
PORT = 5001
BUFFER_SIZE = 4096
DISCONNECT_MSG = b"__DISCONNECT__"

waiting = None  # Maximal ein wartender Client
lock = threading.Lock()

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
        try: self.conn.close()
        except: pass

def handle_client(client: Client):
    global waiting
    conn, addr = client.conn, client.addr
    try:
        # Warte auf JOIN oder LEAVE
        line = b""
        while not line.endswith(b"\n"):
            part = conn.recv(1)
            if not part:
                client.close()
                return
            line += part

        if line == b"JOIN\n":
            log(f"{addr} joined")
            with lock:
                global waiting
                if waiting is None:
                    waiting = client
                    log(f"{addr} wartet auf Partner...")
                else:
                    partner = waiting
                    waiting = None
                    client.partner = partner
                    partner.partner = client
                    # Beide Clients verbinden
                    threading.Thread(target=relay, args=(client, partner), daemon=True).start()
                    threading.Thread(target=relay, args=(partner, client), daemon=True).start()
                    log(f"Paired {addr} <-> {partner.addr}")

        elif line == b"LEAVE\n":
            log(f"{addr} left before pairing")
            client.close()
            with lock:
                if waiting is client:
                    waiting = None

        else:
            log(f"{addr} sent unknown command: {line}")
            client.close()

    except Exception as e:
        log(f"Error {addr}: {e}")
        client.close()
        with lock:
            if waiting is client:
                waiting = None

def relay(src: Client, dst: Client):
    """Leite Daten von src -> dst weiter"""
    try:
        while True:
            data = src.conn.recv(BUFFER_SIZE)
            if not data or data == DISCONNECT_MSG:
                break
            dst.conn.sendall(data)
    except Exception as e:
        log(f"Relay error {src.addr}->{dst.addr}: {e}")
    finally:
        log(f"{src.addr} disconnected")
        src.close()
        if dst.alive:
            try: dst.conn.sendall(DISCONNECT_MSG)
            except: pass
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
