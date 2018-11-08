import os
import sys


# Append module root directory to sys.path.
# Ref: https://stackoverflow.com/a/23386287/1466456
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
