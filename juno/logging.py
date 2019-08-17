import logging
import sys
from datetime import datetime
from logging.handlers import TimedRotatingFileHandler
from typing import List, Optional

import simplejson as json

from juno.utils import home_path


def create_handlers(log_format: str, log_outputs: List[str]) -> List[logging.Handler]:
    # We make a copy in order not to mutate the input.
    log_outputs = log_outputs[:]

    handlers: List[logging.handler] = []

    if 'stdout' in log_outputs:
        handlers.append(logging.StreamHandler(stream=sys.stdout))
        log_outputs.remove('stdout')
    if 'file' in log_outputs:
        handlers.append(
            TimedRotatingFileHandler(home_path('logs') / 'log', when='midnight', utc=True)
        )
        log_outputs.remove('file')
    if len(log_outputs) > 0:
        # TODO: Use Python 3.8 debug formatting.
        raise NotImplementedError(f'log_outputs={log_outputs}')

    if log_format == 'default':
        pass
    elif log_format == 'azure':
        for handler in handlers:
            handler.setFormatter(AzureFormatter())
    else:
        raise NotImplementedError(f'log_format={log_format}')

    return handlers


class AzureFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return json.dumps({
            'severity': record.levelname,
            'time': datetime.utcfromtimestamp(record.created).isoformat() + 'Z',
            'message': f'{record.name}: {super().format(record)}'
        })
