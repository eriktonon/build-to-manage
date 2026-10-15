import json
import logging
from datetime import datetime, timezone
from random import choice

USERS = ["sre-operator", "payment-worker", "autonomous-agent"]
IPS = ["10.240.0.12", "127.0.0.1", "192.168.3.109"]
TRACE_IDS = [
    "4bf92f3577b34da6a3ce929d0e0e4736",
    "8a3c60f7d188f8fa79d48a391a778fa6",
]


class TransactionIDContextFilter(logging.Filter):
    """Injects IBM Build to Manage contextual telemetry fields into Python log records."""

    def filter(self, record):
        record.ip = getattr(record, "ip", choice(IPS))
        record.user = getattr(record, "user", choice(USERS))
        record.trace_id = getattr(record, "trace_id", choice(TRACE_IDS))
        record.event_code = getattr(record, "event_code", "BTM-LOG-1000")
        return True


class BTMJsonFormatter(logging.Formatter):
    """Formats Python LogRecord as a single-line IBM Build to Manage JSON log entry."""

    def format(self, record):
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "severity": record.levelname,
            "service": record.name,
            "release": {"version": "2.0.0", "commit_sha": "b2m-carbon-v11"},
            "trace_id": getattr(record, "trace_id", "unknown"),
            "transaction_id": f"tx-{getattr(record, 'trace_id', '000000000000')[:12]}",
            "event_code": getattr(record, "event_code", "BTM-LOG-1000"),
            "client_ip": getattr(record, "ip", "127.0.0.1"),
            "principal": getattr(record, "user", "system"),
            "message": record.getMessage(),
        }
        return json.dumps(payload)


def create_btm_logger(name: str = "btm.service3.audit") -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(BTMJsonFormatter())
        logger.addHandler(handler)
        logger.addFilter(TransactionIDContextFilter())
    return logger


if __name__ == "__main__":
    log = create_btm_logger()
    log.debug("Diagnostic trace context initialized")
    log.info("Settlement batch validated with parameter=%s", "ISO20022-PIX")
