from setuptools import find_packages, setup

setup(
    name='juno',
    version='0.2.0',
    packages=find_packages(),
    install_requires=[
        'aiohttp',
        'aiosqlite',
        'backoff',
        'simplejson'
    ],
    extras_require={
        'dev': [
            'flake8',
            'mypy',
            'pytest',
            'pytest-aiohttp'
        ]
    })
