import logging
import os
import sys

from juno.logging import create_handlers
from juno.path import load_text_file

logging.basicConfig(
    handlers=create_handlers("color", ["stdout"]),
    level=logging.getLevelName(os.getenv("JUNO__LOG_LEVEL", "INFO").upper()),
)

script_path = sys.argv[1]

# Remove self from args as if the script was called directly.
sys.argv.pop(0)

# Append module root directory to sys.path. Takes precedence over existing path.
# Ref: https://stackoverflow.com/a/23386287/1466456
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

exec(load_text_file(script_path))

logging.info("done")
