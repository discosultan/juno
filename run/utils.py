import os
import sys


def insert_root_to_path():
    # Append module root directory to sys.path. Takes precedense over existing path.
    # Ref: https://stackoverflow.com/a/23386287/1466456
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
