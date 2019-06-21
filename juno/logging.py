import logging
import sys
from datetime import datetime

import simplejson as json


def create_handler(log_format: str) -> logging.Handler:
    handler = logging.StreamHandler(stream=sys.stdout)
    if log_format == 'azure':
        handler.setFormatter(AzureFormatter())
    return handler


class AzureFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return json.dumps({
            'severity': record.levelname,
            'time': datetime.fromtimestamp(record.created).isoformat() + 'Z',
            'message': f'{record.name}: {super().format(record)}'})
