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
    app.config["LOCAL_DEV_BYPASS_AUTH"] = True
    app.register_blueprint(create_blueprint())
    try:
        from ..tess_tce import create_blueprint as create_tess_tce_blueprint

        app.register_blueprint(create_tess_tce_blueprint())
        app.config["TPF_LOCAL_TESS_TCE_AVAILABLE"] = True
    except ModuleNotFoundError as err:
        LOGGER.warning("TESS TCE blueprint not available in local runner: missing dependency %s", err.name)
        app.config["TPF_LOCAL_TESS_TCE_AVAILABLE"] = False
    return app


app = create_app()


if __name__ == "__main__":
    configure_logging()
    LOGGER.info("TPF local server running at http://%s:%s/tpf/", HOST, PORT)
    LOGGER.info("TPF health endpoint available at http://%s:%s/tpf/health", HOST, PORT)
    if app.config.get("TPF_LOCAL_TESS_TCE_AVAILABLE", False):
        LOGGER.info("TESS TCE local page available at http://%s:%s/agata/tess-tce/", HOST, PORT)
        LOGGER.info("TESS TCE health endpoint available at http://%s:%s/agata/tess-tce/api/health", HOST, PORT)
    else:
        LOGGER.info("TESS TCE local page not registered in this environment.")
    app.run(host=HOST, port=PORT, debug=settings.local_debug)
