import logging
import os
import sys

from juno.logging import create_handlers

logging.basicConfig(
    handlers=create_handlers('colored', ['stdout']),
    level=logging.getLevelName(os.getenv('JUNO__LOG_LEVEL', 'INFO').upper()),
)

script_path = sys.argv[1]

# Remove self from args as if the script was called directly.
sys.argv.pop(0)

# Append module root directory to sys.path. Takes precedense over existing path.
# Ref: https://stackoverflow.com/a/23386287/1466456
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

exec(open(script_path).read())

logging.info('done')
