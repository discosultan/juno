from setuptools import find_packages, setup

setup(
    name="juno",
    version="0.5.0",
    packages=find_packages(),
    python_requires=">= 3.11",
    install_requires=[
        "aiohttp",
        "aiolimiter",
        "asyncstdlib",
        "colorlog",
        "mergedeep",
        "more-itertools",
        "multidict",
        "numpy",
        "pandas",
        "pytweening",
        "pyyaml",
        "simplejson",
        "tenacity",
        "typing-inspect",
    ],
    extras_require={
        "api": [
            "aiohttp",
            "aiohttp_cors",
        ],
        "dev": [
            "black",
            "flake8",
            "flake8-bugbear",
            "flake8-comprehensions",
            "flake8-isort",
            "isort",
            "mypy",
            "pytest",
            "pytest-aiohttp",
            "pytest-asyncio",
            "pytest-lazy-fixture",
            "pytest-mock",
            "types-pyyaml",
            "types-setuptools",
            "types-simplejson",
        ],
        "discord": [
            "discord.py",
        ],
        "plotly": [
            "plotly",
        ],
        "slack": [
            "slack_sdk",
        ],
    },
)
