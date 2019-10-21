from setuptools import find_packages, setup

setup(
    name='juno',
    version='0.5.0',
    packages=find_packages(),
    include_package_data=True,
    install_requires=[
        'aiohttp',
        'aiosqlite',
        'backoff',
        'cffi',
        'colorlog',
        'deap',
        'numpy',  # Also implicitly required by deap.
        'pandas',
        'python-dateutil',
        'simplejson',
    ],
    extras_require={
        'dev': [
            'flake8',
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
