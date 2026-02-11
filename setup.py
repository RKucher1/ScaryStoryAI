"""Package setup."""

from setuptools import find_packages, setup

setup(
    name="scarystoryai",
    version="1.0.0",
    packages=find_packages(),
    python_requires=">=3.10",
    install_requires=[
        "praw>=7.7.0",
        "pyyaml>=6.0",
        "pydub>=0.25.1",
    ],
    extras_require={
        "coqui": ["TTS>=0.22.0"],
        "elevenlabs": ["elevenlabs>=1.0.0"],
        "bark": ["bark>=0.1.0", "scipy>=1.11.0"],
        "dev": ["pytest>=7.4.0"],
    },
    entry_points={
        "console_scripts": [
            "scarystory=scarystory.cli:main",
        ],
    },
)
