from setuptools import setup, find_packages


setup(
    name='juno',
    version='0.2.0',
    packages=find_packages(),
    install_requires=[
        'aiohttp',
        'aiosqlite',
        'backoff',
        'numpy',
        'simplejson'
    ],
    extras_require={
        'dev': [
            'pytest'
        ]
    })
