import socket
import threading
import time
import struct

HOST = "0.0.0.0"
PORT = 5001
BUFFER_SIZE = 65536

lock = threading.Lock()
waiting_clients = []
active_pairs = []

def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}")

class Client:
    def __init__(self, conn, addr):
        self.conn = conn
        self.addr = addr
        self.partner = None
        self.alive = True
        self.paired = False
        
    def close(self):
        if not self.alive:
            return
        self.alive = False
        try:
            self.conn.shutdown(socket.SHUT_RDWR)
        except:
            pass
        try:
            self.conn.close()
        except:
            pass

def handle_client(conn, addr):
    client = Client(conn, addr)
    log(f"New connection from {addr}")
    
    try:
        conn.settimeout(5.0)
        cmd = conn.recv(16).strip()
        
        if cmd != b"JOIN":
            log(f"{addr} sent invalid command: {cmd}")
            client.close()
            return
            
        log(f"{addr} requested to join")
        
        partner = None
        with lock:
            waiting_clients_copy = [c for c in waiting_clients if c.alive]
            waiting_clients.clear()
            waiting_clients.extend(waiting_clients_copy)
            
            if waiting_clients:
                partner = waiting_clients.pop(0)
                if not partner.alive:
                    partner = None
                    
            if partner:
                client.partner = partner
                partner.partner = client
                client.paired = True
                partner.paired = True
                active_pairs.append((client, partner))
                log(f"Paired {client.addr} <-> {partner.addr}")
                
                try:
                    client.conn.sendall(b"PAIRED\n")
                    partner.conn.sendall(b"PAIRED\n")
                except:
                    log(f"Failed to notify pair {client.addr} <-> {partner.addr}")
                    cleanup_pair(client, partner)
                    return
                    
                threading.Thread(target=relay_bidirectional, args=(client, partner), daemon=True).start()
            else:
                waiting_clients.append(client)
                log(f"{addr} waiting for partner...")
                try:
                    client.conn.sendall(b"WAITING\n")
                except:
                    log(f"Failed to notify {addr} of waiting status")
                    with lock:
                        if client in waiting_clients:
                            waiting_clients.remove(client)
                    client.close()
                    return
                
                wait_for_pair(client)
                    
    except Exception as e:
        log(f"Error handling {addr}: {e}")
        client.close()
        with lock:
            if client in waiting_clients:
                waiting_clients.remove(client)

def wait_for_pair(client):
    try:
        client.conn.settimeout(0.5)
        while client.alive and not client.paired:
            try:
                data = client.conn.recv(1)
                if not data:
                    log(f"{client.addr} disconnected while waiting")
                    client.close()
                    with lock:
                        if client in waiting_clients:
                            waiting_clients.remove(client)
                    break
            except socket.timeout:
                continue
            except:
                log(f"{client.addr} connection error while waiting")
                client.close()
                with lock:
                    if client in waiting_clients:
                        waiting_clients.remove(client)
                break
    except Exception as e:
        log(f"Error in wait_for_pair for {client.addr}: {e}")
        client.close()
        with lock:
            if client in waiting_clients:
                waiting_clients.remove(client)

def relay_bidirectional(client1, client2):
    def relay_one_way(src, dst):
        try:
            src.conn.settimeout(None)
            while src.alive and dst.alive:
                try:
                    data = src.conn.recv(BUFFER_SIZE)
                    if not data:
                        break
                    dst.conn.sendall(data)
                except socket.timeout:
                    continue
                except Exception as e:
                    break
        except Exception as e:
            pass
        finally:
            cleanup_pair(src, dst)
    
    t1 = threading.Thread(target=relay_one_way, args=(client1, client2), daemon=True)
    t2 = threading.Thread(target=relay_one_way, args=(client2, client1), daemon=True)
    t1.start()
    t2.start()

def cleanup_pair(client1, client2):
    with lock:
        if (client1, client2) in active_pairs:
            active_pairs.remove((client1, client2))
        if (client2, client1) in active_pairs:
            active_pairs.remove((client2, client1))
    
    log(f"Cleaning up pair {client1.addr} <-> {client2.addr}")
    client1.close()
    client2.close()

def cleanup_thread():
    while True:
        time.sleep(1.0)
        with lock:
            before_count = len(waiting_clients)
            waiting_clients[:] = [c for c in waiting_clients if c.alive and not c.paired]
            after_count = len(waiting_clients)
            if before_count != after_count:
                log(f"Cleaned up {before_count - after_count} dead/paired waiting clients")

def main():
    threading.Thread(target=cleanup_thread, daemon=True).start()
    
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((HOST, PORT))
    srv.listen(100)
    log(f"Relay server listening on {HOST}:{PORT}")
    
    while True:
        try:
            conn, addr = srv.accept()
            threading.Thread(target=handle_client, args=(conn, addr), daemon=True).start()
        except Exception as e:
            log(f"Accept error: {e}")

if __name__ == "__main__":
    main()
