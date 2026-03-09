from __future__ import annotations

import logging
import os

from gtpweb import create_app


app = create_app()
logger = logging.getLogger(__name__)


if __name__ == "__main__":
    host = "0.0.0.0"
    port = int(os.getenv("PORT", "8000"))
    debug = os.getenv("FLASK_DEBUG", "1").strip() in {"1", "true", "yes", "on"}
    logger.info("启动 Web 服务: host=%s port=%s debug=%s", host, port, debug)
    app.run(host=host, port=port, debug=debug)
