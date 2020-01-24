from setuptools import find_packages, setup

setup(
    name='juno',
    version='0.5.0',
    packages=find_packages(),
    include_package_data=True,
    install_requires=[
        'aiohttp',
        # This is a fork of original aiolimiter which adds logging support.
        'aiolimiter @ git+https://github.com/discosultan/aiolimiter@master#egg=aiolimiter',
        'cffi',
        'colorlog',
        'deap',
        'numpy',
        'pandas',
        'python-dateutil',
        'simplejson',
        'tenacity',
    ],
    extras_require={
        'dev': [
            'flake8',
            'flake8-bugbear',
            'flake8-comprehensions',
            'flake8-isort',
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
