import inspect
import logging
import zlib

from juno import indicators

for name, _indicator in inspect.getmembers(indicators, inspect.isclass):
    checksum = zlib.adler32(name.lower().encode())
    logging.info(f'{name} - {checksum}')
