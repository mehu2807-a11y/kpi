from waitress import serve
from app import app
import socket

def get_local_ip():
    try:
        # Create a dummy socket to determine the local IP route
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
        return local_ip
    except Exception:
        return "127.0.0.1"

if __name__ == '__main__':
    local_ip = get_local_ip()
    port = 5000
    print("=" * 60)
    print("?? BusinessIntelligence.ai Dashboard is LIVE (Production Mode)")
    print("=" * 60)
    print(f"? Local URL (This PC):    http://localhost:{port}/dashboard")
    print(f"? Network URL (LAN):      http://{local_ip}:{port}/dashboard")
    print("=" * 60)
    print("Press CTRL+C to stop the server.")
    
    # Waitress is a production-quality WSGI server for Windows.
    # We bind it to '0.0.0.0' to allow access from any device on the network.
    serve(app, host='0.0.0.0', port=port, threads=6)
