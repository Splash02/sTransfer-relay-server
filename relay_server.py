import socket
import threading
import time
import queue

HOST = "0.0.0.0"
PORT = 5001
BUFFER_SIZE = 65536

waiting_queue = queue.Queue()
active_pairs = []
lock = threading.Lock()

def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}")

class ClientConnection:
    def __init__(self, conn, addr):
        self.conn = conn
        self.addr = addr
        self.alive = True
        
    def close(self):
        if not self.alive:
            return
        self.alive = False
        try:
            self.conn.close()
        except:
            pass

def handle_new_client(conn, addr):
    client = ClientConnection(conn, addr)
    log(f"New connection from {addr}")
    
    try:
        conn.settimeout(3.0)
        data = conn.recv(16).strip()
        
        if data != b"JOIN":
            log(f"{addr} invalid command: {data}")
            client.close()
            return
        
        log(f"{addr} joining queue")
        waiting_queue.put(client)
        
    except Exception as e:
        log(f"Error with {addr}: {e}")
        client.close()

def matchmaker():
    log("Matchmaker started")
    while True:
        try:
            client1 = waiting_queue.get(timeout=1.0)
            
            if not client1.alive:
                log(f"Skipping dead client {client1.addr}")
                continue
            
            try:
                client1.conn.sendall(b"WAITING\n")
                log(f"{client1.addr} sent WAITING, looking for partner...")
            except:
                log(f"{client1.addr} failed to send WAITING")
                client1.close()
                continue
            
            client2 = None
            while client2 is None:
                try:
                    potential = waiting_queue.get(timeout=0.1)
                    if potential.alive and potential.addr != client1.addr:
                        client2 = potential
                    else:
                        log(f"Skipping invalid partner candidate")
                except queue.Empty:
                    if not client1.alive:
                        log(f"{client1.addr} died while waiting")
                        break
                    continue
            
            if client2 is None:
                client1.close()
                continue
            
            log(f"Pairing {client1.addr} <-> {client2.addr}")
            
            try:
                client1.conn.sendall(b"PAIRED\n")
                client2.conn.sendall(b"PAIRED\n")
            except Exception as e:
                log(f"Failed to notify pair: {e}")
                client1.close()
                client2.close()
                continue
            
            with lock:
                active_pairs.append((client1, client2))
            
            t1 = threading.Thread(target=relay_data, args=(client1, client2), daemon=True)
            t2 = threading.Thread(target=relay_data, args=(client2, client1), daemon=True)
            t1.start()
            t2.start()
            
        except queue.Empty:
            continue
        except Exception as e:
            log(f"Matchmaker error: {e}")

def relay_data(src, dst):
    try:
        src.conn.settimeout(None)
        while src.alive and dst.alive:
            try:
                data = src.conn.recv(BUFFER_SIZE)
                if not data:
                    break
                dst.conn.sendall(data)
            except Exception as e:
                break
    except Exception as e:
        pass
    finally:
        log(f"Relay ended: {src.addr} -> {dst.addr}")
        src.close()
        dst.close()
        with lock:
            try:
                active_pairs.remove((src, dst))
            except:
                pass
            try:
                active_pairs.remove((dst, src))
            except:
                pass

def cleanup_dead_connections():
    while True:
        time.sleep(5.0)
        with lock:
            count = len(active_pairs)
            log(f"Active pairs: {count}")

def main():
    threading.Thread(target=matchmaker, daemon=True).start()
    threading.Thread(target=cleanup_dead_connections, daemon=True).start()
    
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((HOST, PORT))
    server.listen(100)
    log(f"Relay server listening on {HOST}:{PORT}")
    
    while True:
        try:
            conn, addr = server.accept()
            threading.Thread(target=handle_new_client, args=(conn, addr), daemon=True).start()
        except Exception as e:
            log(f"Accept error: {e}")

if __name__ == "__main__":
    main()
