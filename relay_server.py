import socket
import threading
import os

HOST = '0.0.0.0'
PORT = int(os.environ.get("PORT", 5001))

clients = []

def handle_client(conn, addr):
    global clients
    print(f"[+] Connected: {addr}")
    clients.append(conn)

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
                break
            dst.sendall(data)
    except:
        pass
    finally:
        src.close()
        dst.close()
        print("[*] Relay closed")
        clients.clear()

def main():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.bind((HOST, PORT))
        server.listen(2)
        print(f"[+] Relay server listening on port {PORT}")
        while True:
            conn, addr = server.accept()
            threading.Thread(target=handle_client, args=(conn, addr), daemon=True).start()

if __name__ == "__main__":
    main()