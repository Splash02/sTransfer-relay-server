import socket
import threading
import time
import struct
import json
from collections import deque

HOST = "0.0.0.0"
PORT = 5001
BUFFER_SIZE = 65536
HEARTBEAT_INTERVAL = 5
HEARTBEAT_TIMEOUT = 15

class RelayServer:
    def __init__(self):
        self.waiting_clients = deque()
        self.matched_pairs = {}
        self.client_info = {}
        self.lock = threading.Lock()
        
    def handle_client(self, client_socket, addr):
        client_id = f"{addr[0]}:{addr[1]}"
        print(f"[NEW CONNECTION] {client_id}")
        
        # Optimize socket for large file transfers
        try:
            client_socket.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 1024 * 1024)  # 1MB send buffer
            client_socket.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1024 * 1024)  # 1MB recv buffer
            client_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)  # Disable Nagle
        except:
            pass  # Some systems may not support these options
        
        try:
            with self.lock:
                self.client_info[client_id] = {
                    'socket': client_socket,
                    'addr': addr,
                    'last_heartbeat': time.time(),
                    'partner': None
                }
            
            client_socket.send(b"CONNECTED")
            
            while True:
                try:
                    client_socket.settimeout(1.0)
                    data = client_socket.recv(BUFFER_SIZE)
                    
                    if not data:
                        break
                    
                    # Check if this is a text command or binary data
                    # Text commands: JOIN, HEARTBEAT, LEAVE, FILE:...
                    # Binary data: file chunks with length prefix
                    
                    is_matched = False
                    with self.lock:
                        is_matched = client_id in self.matched_pairs
                    
                    if is_matched and (data[:4] == struct.pack('!I', len(data)-4) or b'\n' not in data[:100] and len(data) > 100):
                        # This looks like binary file data (length-prefixed chunk)
                        self.relay_data(client_id, data)
                    else:
                        # Try to decode as text command
                        try:
                            message = data.decode('utf-8', errors='ignore').strip()
                            
                            if message == "JOIN":
                                self.handle_join(client_id)
                            elif message == "HEARTBEAT":
                                with self.lock:
                                    if client_id in self.client_info:
                                        self.client_info[client_id]['last_heartbeat'] = time.time()
                                client_socket.send(b"HEARTBEAT_ACK")
                            elif message == "LEAVE":
                                break
                            elif message.startswith("FILE:") or b"FILE:" in data:
                                # File header - forward to partner
                                self.relay_data(client_id, data)
                            elif len(data) >= 4:
                                # Could be binary chunk, forward it
                                self.relay_data(client_id, data)
                        except:
                            # If decode fails, it's binary data
                            self.relay_data(client_id, data)
                        
                except socket.timeout:
                    continue
                except Exception as e:
                    print(f"[ERROR] {client_id}: {e}")
                    break
                    
        except Exception as e:
            print(f"[ERROR] Connection error for {client_id}: {e}")
        finally:
            self.disconnect_client(client_id)
            
    def handle_join(self, client_id):
        with self.lock:
            if client_id not in self.client_info:
                return
                
            if self.waiting_clients:
                partner_id = self.waiting_clients.popleft()
                
                if partner_id in self.client_info:
                    self.matched_pairs[client_id] = partner_id
                    self.matched_pairs[partner_id] = client_id
                    
                    self.client_info[client_id]['partner'] = partner_id
                    self.client_info[partner_id]['partner'] = client_id
                    
                    try:
                        partner_socket = self.client_info[partner_id]['socket']
                        client_socket = self.client_info[client_id]['socket']
                        
                        partner_socket.send(b"MATCHED")
                        client_socket.send(b"MATCHED")
                        
                        print(f"[MATCHED] {client_id} <-> {partner_id}")
                    except Exception as e:
                        print(f"[ERROR] Failed to notify match: {e}")
                        self.disconnect_client(client_id)
                        self.disconnect_client(partner_id)
                else:
                    self.waiting_clients.append(client_id)
                    self.client_info[client_id]['socket'].send(b"WAITING")
                    print(f"[WAITING] {client_id}")
            else:
                self.waiting_clients.append(client_id)
                self.client_info[client_id]['socket'].send(b"WAITING")
                print(f"[WAITING] {client_id}")
                
    def relay_data(self, sender_id, data):
        with self.lock:
            if sender_id in self.matched_pairs:
                partner_id = self.matched_pairs[sender_id]
                if partner_id in self.client_info:
                    try:
                        partner_socket = self.client_info[partner_id]['socket']
                        partner_socket.send(data)
                    except Exception as e:
                        print(f"[ERROR] Failed to relay data: {e}")
                        self.disconnect_client(sender_id)
                        self.disconnect_client(partner_id)
                        
    def disconnect_client(self, client_id):
        with self.lock:
            if client_id in self.client_info:
                partner_id = self.client_info[client_id].get('partner')
                
                try:
                    self.client_info[client_id]['socket'].close()
                except:
                    pass
                
                del self.client_info[client_id]
                
                if partner_id and partner_id in self.client_info:
                    try:
                        self.client_info[partner_id]['socket'].send(b"PARTNER_DISCONNECTED")
                        self.client_info[partner_id]['partner'] = None
                    except:
                        pass
                    
                    if partner_id in self.matched_pairs:
                        del self.matched_pairs[partner_id]
                        
                if client_id in self.matched_pairs:
                    del self.matched_pairs[client_id]
                    
                if client_id in self.waiting_clients:
                    self.waiting_clients.remove(client_id)
                    
                print(f"[DISCONNECTED] {client_id}")
                
    def check_heartbeats(self):
        while True:
            time.sleep(HEARTBEAT_INTERVAL)
            current_time = time.time()
            
            with self.lock:
                disconnected = []
                for client_id, info in list(self.client_info.items()):
                    if current_time - info['last_heartbeat'] > HEARTBEAT_TIMEOUT:
                        disconnected.append(client_id)
                        
            for client_id in disconnected:
                print(f"[TIMEOUT] {client_id}")
                self.disconnect_client(client_id)
                
    def start(self):
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_socket.bind((HOST, PORT))
        server_socket.listen(5)
        
        print(f"[STARTED] Relay server listening on {HOST}:{PORT}")
        
        heartbeat_thread = threading.Thread(target=self.check_heartbeats, daemon=True)
        heartbeat_thread.start()
        
        try:
            while True:
                client_socket, addr = server_socket.accept()
                thread = threading.Thread(target=self.handle_client, args=(client_socket, addr))
                thread.daemon = True
                thread.start()
        except KeyboardInterrupt:
            print("\n[SHUTDOWN] Server shutting down...")
        finally:
            server_socket.close()

if __name__ == "__main__":
    server = RelayServer()
    server.start()
