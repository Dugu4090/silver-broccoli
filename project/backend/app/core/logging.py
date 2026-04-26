import logging
import sys
import structlog
from app.config import settings


def configure_logging():
    logging.basicConfig(
        format="%(message)s", stream=sys.stdout, level=settings.LOG_LEVEL,
    )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
        ),
        logger_factory=structlog.PrintLoggerFactory(),
    )


log = structlog.get_logger()
