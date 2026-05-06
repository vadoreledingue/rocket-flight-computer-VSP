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
            "Adafruit-Blinka",
            "adafruit-circuitpython-bmp280",
            "adafruit-circuitpython-mpu6050",
            "smbus2",
            "RPi.GPIO",
            "picamera2",
            "Pillow",
        ],
    },
    entry_points={
        "console_scripts": [
            "rocket-flight=flight.main:main",
            "rocket-dashboard=dashboard.app:main",
        ],
    },
)
