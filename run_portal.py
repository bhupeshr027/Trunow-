import os
import threading
import webbrowser
from pathlib import Path

appdata_root = Path(os.getenv("LOCALAPPDATA", Path.home()))
data_dir = appdata_root / "TRUNOWPortal"
data_dir.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("DATABASE_PATH", str(data_dir / "trunow.db"))

from app import app


def open_browser():
    webbrowser.open("http://127.0.0.1:5000")


if __name__ == "__main__":
    threading.Timer(1.5, open_browser).start()
    app.run(host="127.0.0.1", port=5000, debug=False, use_reloader=False)
