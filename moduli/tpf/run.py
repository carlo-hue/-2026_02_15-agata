from __future__ import annotations

import logging

from flask import Flask

from .config import settings
from .routes import create_blueprint

LOGGER = logging.getLogger(__name__)
HOST = "127.0.0.1"
PORT = 5010


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.DEBUG if settings.local_debug else logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )


def create_app() -> Flask:
    app = Flask(__name__)
    app.config["SECRET_KEY"] = "tpf-local-dev"
    app.register_blueprint(create_blueprint())
    return app


app = create_app()


if __name__ == "__main__":
    configure_logging()
    LOGGER.info("TPF local server running at http://%s:%s/tpf/", HOST, PORT)
    LOGGER.info("TPF health endpoint available at http://%s:%s/tpf/health", HOST, PORT)
    app.run(host=HOST, port=PORT, debug=settings.local_debug)
