import socket
import threading
import struct
import time

HOST = "0.0.0.0"
PORT = 5001
BUFFER_SIZE = 4096
DISCONNECT_MSG = b"__DISCONNECT__"

lock = threading.Lock()
waiting_clients = []

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
        except: pass

def monitor_waiting():
    while True:
        with lock:
            waiting_clients[:] = [c for c in waiting_clients if c.alive]
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
                    for waiting in waiting_clients:
                        if waiting.alive and waiting != client:
                            client.partner = waiting
                            waiting.partner = client
                            waiting_clients.remove(waiting)
                            paired = True
                            # Notify both clients
                            try:
                                client.conn.sendall(b"PAIRED\n")
                                waiting.conn.sendall(b"PAIRED\n")
                            except: pass
                            threading.Thread(target=relay, args=(client, waiting), daemon=True).start()
                            threading.Thread(target=relay, args=(waiting, client), daemon=True).start()
                            log(f"Paired {client.addr} <-> {waiting.addr}")
                            break
                    if not paired:
                        waiting_clients.append(client)
                        try:
                            client.conn.sendall(b"WAITING\n")
                        except: pass
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
    try:
        while src.alive and dst.alive:
            try:
                # Zuerst 4 Byte Header einlesen
                hdr = src.conn.recv(4)
                if not hdr:
                    break
                if hdr == DISCONNECT_MSG[:4]:
                    rest = src.conn.recv(len(DISCONNECT_MSG)-4)
                    if hdr+rest == DISCONNECT_MSG:
                        break
                length = struct.unpack(">I", hdr)[0]
                # Meta auslesen
                meta = src.conn.recv(length)
                dst.conn.sendall(hdr + meta)  # Weiterleiten
                fname, fsize, ftype = meta.decode().split("|")
                fsize = int(fsize)
                # Datei-Daten weiterleiten
                sent = 0
                while sent < fsize:
                    chunk = src.conn.recv(min(BUFFER_SIZE, fsize - sent))
                    if not chunk:
                        break
                    dst.conn.sendall(chunk)
                    sent += len(chunk)
            except:
                break
    finally:
        log(f"{src.addr} disconnected")
        src.close()
        if dst.alive:
            try:
                dst.conn.sendall(DISCONNECT_MSG)
            except: pass
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
