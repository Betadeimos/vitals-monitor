from setuptools import setup

setup(
    name="vitals",
    version="0.1.0",
    author="Gemini CLI",
    description="Lightweight terminal watchdog for 3ds Max",
    py_modules=["vitals", "vitals_core"],
    install_requires=[
        "psutil",
    ],
    entry_points={
        "console_scripts": [
            "vitals=vitals:main",
        ],
    },
)
