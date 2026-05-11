from setuptools import setup

setup(
    name="vitals",
    version="0.2.0",
    author="Davide Chincoli",
    description="Lightweight terminal watchdog and time tracker for 3ds Max",
    py_modules=["vitals", "vitals_core", "vitals_stats"],
    install_requires=[
        "psutil",
    ],
    entry_points={
        "console_scripts": [
            "vitals=vitals:main",
        ],
    },
)
