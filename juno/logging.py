import logging
import sys
from datetime import datetime
from logging.handlers import TimedRotatingFileHandler
from typing import Optional

from colorlog import ColoredFormatter

from juno import json
from juno.path import home_path

disabled_log = logging.Logger(name="disabled")
disabled_log.disabled = True


def create_handlers(
    log_format: str = "default",
    log_outputs: list[str] = ["stdout"],
    # The following are used when `log_outputs` includes 'file'.
    log_directory: str = "logs",
    log_backup_count: int = 0,
) -> list[logging.Handler]:
    # We make a copy in order not to mutate the input.
    log_outputs = log_outputs[:]

    handlers: list[logging.Handler] = []

    if "stdout" in log_outputs:
        handlers.append(logging.StreamHandler(stream=sys.stdout))
        log_outputs.remove("stdout")
    if "file" in log_outputs:
        handlers.append(
            TimedRotatingFileHandler(
                home_path(log_directory) / "log",
                when="midnight",
                utc=True,
                backupCount=log_backup_count,
            )
        )
        log_outputs.remove("file")
    if len(log_outputs) > 0:
        raise NotImplementedError(f"{log_outputs=}")

    formatter: Optional[logging.Formatter] = None
    if log_format == "default":
        pass
    elif log_format == "color":
        formatter = ColoredFormatter(
            fmt="%(log_color)s%(levelname)s:%(name)s:%(reset)s%(message)s",
            log_colors={
                "DEBUG": "cyan",
                "INFO": "green",
                "WARNING": "yellow",
                "ERROR": "red",
                "CRITICAL": "red",
            },
        )
    elif log_format == "json":
        formatter = JsonFormatter()
    else:
        raise NotImplementedError(f"{log_format=}")

    if formatter:
        for handler in handlers:
            handler.setFormatter(formatter)

    return handlers


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return json.dumps(
            {
                "severity": record.levelname,
                "time": datetime.utcfromtimestamp(record.created).isoformat() + "Z",
                "message": f"{record.name}: {super().format(record)}",
            }
        )
