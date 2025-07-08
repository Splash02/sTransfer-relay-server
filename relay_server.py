import socket, threading, queue, time

HOST         = '0.0.0.0'
PORT         = 5001
CMD_JOIN     = b"JOIN\n"
CMD_LEAVE    = b"LEAVE\n"
BUFFER_SIZE  = 4096

waiting = queue.Queue()
active  = []
lock    = threading.Lock()

def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}")

def handle_client(conn, addr):
    """
    Liest zuerst JOIN/LEAVE-Befehle, bevor es in die Pairing-Queue kommt.
    """
    log(f"Client up: {addr}")
    try:
        line = b""
        while not line.endswith(b"\n"):
            part = conn.recv(1)
            if not part:
                conn.close()
                return
            line += part
        if line == CMD_JOIN:
            waiting.put((conn, addr))
            log(f"{addr} JOIN")
            # Jetzt verbleibt der Socket in der Queue bis pairing
        else:
            conn.close()
    except:
        pass

def is_closed(conn):
    try:
        conn.settimeout(0.01)
        data = conn.recv(1, socket.MSG_PEEK)
        conn.settimeout(None)
        return False
    except:
        conn.settimeout(None)
        return True

def relay(a, b, addr_a, addr_b):
    """
    Relay loop: bricht bei LEAVE oder Socket-Close ab.
    """
    try:
        while True:
            data = a.recv(BUFFER_SIZE)
            if not data or data == CMD_LEAVE:
                log(f"{addr_a} LEAVE")
                break
            b.sendall(data)
    except Exception as e:
        log(f"Error {addr_a}->{addr_b}: {e}")
    finally:
        cleanup(a,b,addr_a,addr_b)

def cleanup(a,b,addr_a,addr_b):
    for s in (a,b): 
        try: s.close()
        except: pass
    with lock:
        active[:] = [p for p in active if addr_a not in p and addr_b not in p]
    log(f"Cleanup {addr_a} & {addr_b}")

def matcher():
    while True:
        conn1, addr1 = waiting.get()
        # wenn Client schon gone, skip
        if is_closed(conn1):
            log(f"Skipping closed {addr1}")
            continue

        conn2, addr2 = waiting.get()
        if is_closed(conn2):
            waiting.put((conn1, addr1))
            log(f"Skipping closed {addr2}")
            continue

        with lock:
            active.append((addr1, addr2))
        log(f"Pairing {addr1} <-> {addr2}")
        threading.Thread(target=relay, args=(conn1,conn2,addr1,addr2), daemon=True).start()
        threading.Thread(target=relay, args=(conn2,conn1,addr2,addr1), daemon=True).start()

def main():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR,1)
    server.bind((HOST,PORT))
    server.listen(10)
    log(f"Relay listening on {HOST}:{PORT}")
    threading.Thread(target=matcher, daemon=True).start()
    while True:
        conn, addr = server.accept()
        threading.Thread(target=handle_client, args=(conn,addr), daemon=True).start()

if __name__=="__main__":
    main()
