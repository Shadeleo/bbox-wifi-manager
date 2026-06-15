import logging
import os
import webbrowser
import threading

from dotenv import load_dotenv

logging.basicConfig(level=logging.DEBUG, format="%(name)s %(levelname)s %(message)s")
logging.getLogger("urllib3").setLevel(logging.WARNING)

load_dotenv()

from app import create_app

app = create_app()


def _open_browser(port: int) -> None:
    webbrowser.open(f"http://localhost:{port}")


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    print(f"Interface disponible sur http://localhost:{port}")
    threading.Timer(1.0, _open_browser, args=[port]).start()
    app.run(host="0.0.0.0", port=port, debug=False)
