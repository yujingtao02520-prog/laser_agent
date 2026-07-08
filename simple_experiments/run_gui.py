import os
import sys
import threading
import time
import webbrowser
import uvicorn

def open_browser():
    time.sleep(1.5)
    url = "http://127.0.0.1:8000/"
    print(f"\n[*] Automatically opening browser: {url}")
    webbrowser.open(url)

if __name__ == "__main__":
    # Add src to system path
    src_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "src")
    sys.path.append(src_dir)
    
    # Launch browser thread
    threading.Thread(target=open_browser, daemon=True).start()
    
    print("[*] Starting Simple Laser Cutting Experiment Logger on http://127.0.0.1:8000")
    uvicorn.run("gui_server:app", host="127.0.0.1", port=8000, reload=False)
