import socket
import threading
import time

HOST        = '0.0.0.0'
PORT        = 5001
CMD_JOIN    = b"JOIN\n"
CMD_LEAVE   = b"LEAVE\n"
BUFFER_SIZE = 4096

waiting_list = []        # Liste der wartenden Sockets
active_pairs = []        # Liste der aktuell gepaarten Adressen
lock = threading.Lock()

def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}")

def handle_client(conn, addr):
    """
    1) Liest JOIN oder schließt bei anderem
    2) Fügt JOIN-Socket zur waiting_list hinzu
    3) Startet monitor, um LEAVE vor Pairing zu erkennen
    """
    try:
        line = b""
        while not line.endswith(b"\n"):
            part = conn.recv(1)
            if not part:
                conn.close()
                return
            line += part
        if line != CMD_JOIN:
            conn.close()
            return

        with lock:
            waiting_list.append((conn, addr))
        log(f"{addr} JOIN → added to waiting_list")

        # Monitor-Thread, um LEAVE vor dem Pairing zu erfassen
        threading.Thread(target=monitor_waiting, args=(conn, addr), daemon=True).start()

    except Exception as e:
        log(f"handle_client error {addr}: {e}")
        conn.close()

def monitor_waiting(conn, addr):
    """
    Wartet auf LEAVE oder Socket-Close, **vor** Pairing.
    Entfernt den Client aus waiting_list.
    """
    try:
        while True:
            data = conn.recv(BUFFER_SIZE)
            if not data or data == CMD_LEAVE:
                with lock:
                    # entferne alle Einträge mit dieser conn
                    waiting_list[:] = [(c,a) for c,a in waiting_list if c is not conn]
                log(f"{addr} LEAVE before pairing → removed from waiting_list")
                conn.close()
                return
            # sonst ignorieren (z.B. Datei-Daten nach Pairing)
    except:
        with lock:
            waiting_list[:] = [(c,a) for c,a in waiting_list if c is not conn]
        log(f"{addr} disconnected before pairing")
        try: conn.close()
        except: pass

def is_closed(conn):
    try:
        conn.settimeout(0.01)
        _ = conn.recv(1, socket.MSG_PEEK)
        conn.settimeout(None)
        return False
    except:
        conn.settimeout(None)
        return True

def relay(src, dst, addr_src, addr_dst):
    """
    Relay-Loop: bricht bei LEAVE oder Verbindungsende ab.
    """
    try:
        while True:
            data = src.recv(BUFFER_SIZE)
            if not data or data == CMD_LEAVE:
                log(f"{addr_src} LEAVE during transfer")
                break
            dst.sendall(data)
    except Exception as e:
        log(f"Relay error {addr_src}->{addr_dst}: {e}")
    finally:
        cleanup(src, dst, addr_src, addr_dst)

def cleanup(a, b, addr_a, addr_b):
    for s in (a, b):
        try: s.close()
        except: pass
    with lock:
        active_pairs[:] = [p for p in active_pairs if addr_a not in p and addr_b not in p]
    log(f"Cleaned up pair {addr_a} & {addr_b}")

def matcher():
    """
    Polling-Matcher: sobald zwei wartende Sockets verfügbar,
    werden sie gepaart.
    """
    while True:
        with lock:
            # Filter geschlossene Sockets heraus
            waiting_list[:] = [(c,a) for c,a in waiting_list if not is_closed(c)]
            if len(waiting_list) < 2:
                # nichts zu tun
                pass
            else:
                (c1,a1), (c2,a2) = waiting_list.pop(0), waiting_list.pop(0)
                active_pairs.append((a1,a2))
                log(f"Pairing {a1} <-> {a2}")
                # Starte Relay in beide Richtungen
                threading.Thread(target=relay, args=(c1,c2,a1,a2), daemon=True).start()
                threading.Thread(target=relay, args=(c2,c1,a2,a1), daemon=True).start()
        time.sleep(0.1)

def main():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((HOST, PORT))
    server.listen(10)
    log(f"Relay listening on {HOST}:{PORT}")

    threading.Thread(target=matcher, daemon=True).start()

    while True:
        conn, addr = server.accept()
        threading.Thread(target=handle_client, args=(conn, addr), daemon=True).start()

if __name__ == "__main__":
    main()
