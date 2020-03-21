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
        'deap',
        'numpy',
        'pandas',
        'python-dateutil',
        'simplejson',
        'tenacity',
        'typing-inspect',
    ],
    extras_require={
        'dev': [
            'flake8',
            'flake8-bugbear',
            'flake8-comprehensions',
            'flake8-isort',
            'flake8-quotes',
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
        ],
        'plot': [
            'plotly',
        ],
    }
)
