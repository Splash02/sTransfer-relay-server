import socket
import threading
import os

HOST = '0.0.0.0'
PORT = int(os.environ.get("PORT", 5001))

clients = []
clients_lock = threading.Lock()

def handle_client(conn, addr):
    print(f"[+] Connected: {addr}")

    with clients_lock:
        clients.append(conn)
        # Wenn schon 2 Clients verbunden, starten wir Relay
        if len(clients) == 2:
            print("[*] Relaying between two clients...")
            threading.Thread(target=relay, args=(clients[0], clients[1]), daemon=True).start()
            threading.Thread(target=relay, args=(clients[1], clients[0]), daemon=True).start()

def relay(src, dst):
    global clients
    try:
        while True:
            data = src.recv(4096)
            if not data:
                print("[*] Connection closed by peer")
                break
            dst.sendall(data)
    except Exception as e:
        print(f"[!] Relay error: {e}")
    finally:
        with clients_lock:
            # Schließe beide Sockets, wenn einer disconnectet
            for c in clients:
                try:
                    c.shutdown(socket.SHUT_RDWR)
                    c.close()
                except:
                    pass
            clients.clear()
        print("[*] Relay closed")

def main():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((HOST, PORT))
        server.listen(2)
        print(f"[+] Relay server listening on {HOST}:{PORT}")
        while True:
            try:
                conn, addr = server.accept()
                threading.Thread(target=handle_client, args=(conn, addr), daemon=True).start()
            except Exception as e:
                print(f"[!] Accept error: {e}")

if __name__ == "__main__":
    main()
