from setuptools import setup, find_packages


setup(
    name='juno',
    version='0.1.0',
    packages=find_packages(),
    install_requires=[
        'aiohttp',
        'backoff'
    ],
    extras_require={
        'dev': [
            'pytest'
        ]
    })
