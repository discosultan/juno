import logging
import sys
from datetime import datetime
from logging.handlers import TimedRotatingFileHandler
from typing import List

from colorlog import ColoredFormatter

import juno.json as json
from juno.utils import home_path

disabled_log = logging.Logger(name='disabled')
disabled_log.disabled = True


def create_handlers(log_format: str, log_outputs: List[str]) -> List[logging.Handler]:
    # We make a copy in order not to mutate the input.
    log_outputs = log_outputs[:]

    handlers: List[logging.Handler] = []

    if 'stdout' in log_outputs:
        handlers.append(logging.StreamHandler(stream=sys.stdout))
        log_outputs.remove('stdout')
    if 'file' in log_outputs:
        handlers.append(
            TimedRotatingFileHandler(home_path('logs') / 'log', when='midnight', utc=True)
        )
        log_outputs.remove('file')
    if len(log_outputs) > 0:
        raise NotImplementedError(f'{log_outputs=}')

    formatter = None
    if log_format == 'default':
        pass
    elif log_format == 'colored':
        formatter = ColoredFormatter(
            fmt='%(log_color)s%(levelname)s:%(name)s:%(reset)s%(message)s',
            log_colors={
                'DEBUG': 'cyan',
                'INFO': 'green',
                'WARNING': 'yellow',
                'ERROR': 'red',
                'CRITICAL': 'red',
            }
        )
    elif log_format == 'azure':
        formatter = AzureFormatter()
    else:
        raise NotImplementedError(f'{log_format=}')

    if formatter:
        for handler in handlers:
            handler.setFormatter(formatter)

    return handlers


class AzureFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return json.dumps({
            'severity': record.levelname,
            'time': datetime.utcfromtimestamp(record.created).isoformat() + 'Z',
            'message': f'{record.name}: {super().format(record)}'
        })
