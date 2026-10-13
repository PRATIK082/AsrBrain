"""Structured logging + trace helper."""
from __future__ import annotations
import json
import logging
import sys

logging.basicConfig(stream=sys.stdout, level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s :: %(message)s")
log = logging.getLogger("asrbrain")


def log_stage(stage: str, **fields):
    log.info(json.dumps({"stage": stage, **fields})[:2000])
