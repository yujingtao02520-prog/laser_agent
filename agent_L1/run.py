import os
import sys
import threading
import time
import webbrowser
import uvicorn

def open_browser():
    # Wait for uvicorn server to start up
    time.sleep(1.5)
    url = "http://127.0.0.1:8000/"
    print(f"\n[*] Automatically opening browser: {url}")
    webbrowser.open(url)

if __name__ == "__main__":
    # Ensure current directory is on path
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))
    
    # Launch browser thread
    threading.Thread(target=open_browser, daemon=True).start()
    
    print("[*] Starting Laser Cutting Copilot FastAPI Server on http://127.0.0.1:8000")
    uvicorn.run("backend.main:app", host="127.0.0.1", port=8000, reload=False)
