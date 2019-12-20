from setuptools import find_packages, setup

setup(
    name='juno',
    version='0.5.0',
    packages=find_packages(),
    include_package_data=True,
    install_requires=[
        'aiohttp',
        'aiolimiter',
        'cffi',
        'colorlog',
        # A release has not been made for a long time. We pull straight from master for Python 3.8
        # support.
        'deap @ git+ssh://git@github.com/DEAP/deap@master#egg=deap',
        'numpy',  # Also implicitly required by deap.
        'pandas',
        'python-dateutil',
        'simplejson',
        'tenacity',
    ],
    extras_require={
        'dev': [
            'flake8',
            'flake8-comprehensions',
            'isort',
            'mypy',
            'pytest',
            'pytest-aiohttp',
            'pytest-lazy-fixture',
            'rope',
            'yapf',
        ],
        'discord': [
            'discord.py',
            # Required by discord.py. Forces install to latest.
            # https://github.com/Rapptz/discord.py/issues/1996#issuecomment-515816238
            'websockets>=8.0.0',
        ]
    }
)
