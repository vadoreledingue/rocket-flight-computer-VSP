from setuptools import setup, find_packages

setup(
    name="rocket-flight-computer",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "flask",
    ],
    extras_require={
        "pi": [
            "adafruit-circuitpython-bme280",
            "adafruit-circuitpython-bno055",
            "RPi.GPIO",
        ],
    },
    entry_points={
        "console_scripts": [
            "rocket-flight=flight.main:main",
            "rocket-dashboard=dashboard.app:main",
        ],
    },
)
