from setuptools import find_packages, setup

setup(
    name='juno',
    version='0.2.0',
    packages=find_packages(),
    install_requires=[
        'aiohttp',
        'aiosqlite',
        'backoff',
        'deap',
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
        ]
    })
