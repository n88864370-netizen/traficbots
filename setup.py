from setuptools import setup, find_packages

setup(
    name="telegram-bot",
    version="1.0.0",
    packages=find_packages(),
    install_requires=[
        "aiogram==3.10.0",
        "aiohttp==3.9.5",
    ],
    python_requires=">=3.9",
)
