import logging
import os
import threading
import webbrowser

from dotenv import load_dotenv

load_dotenv()

from app import config, create_app  # noqa: E402  (doit suivre load_dotenv)

logging.basicConfig(
    level=getattr(logging, config.log_level(), logging.INFO),
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
logging.getLogger("urllib3").setLevel(logging.WARNING)

app = create_app()


def _open_browser(port: int) -> None:
    webbrowser.open(f"http://localhost:{port}")


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))

    if config.is_production():
        # Werkzeug n'est pas un serveur de production.
        from waitress import serve

        print(f"Interface disponible sur http://0.0.0.0:{port} (waitress)")
        serve(app, host="0.0.0.0", port=port, threads=8)
    else:
        print(f"Interface disponible sur http://localhost:{port}")
        threading.Timer(1.0, _open_browser, args=[port]).start()
        app.run(host="0.0.0.0", port=port, debug=False)
