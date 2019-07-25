from setuptools import find_packages, setup

setup(
    name='juno',
    version='0.3.2',
    packages=find_packages(),
    include_package_data=True,
    install_requires=[
        'aiohttp',
        'aiosqlite',
        'backoff',
        'deap',
        'numpy',  # Required by deap.
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
            'yapf',
        ],
        'discord': [
            'discord.py',
        ]
    }
)
