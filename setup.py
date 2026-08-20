from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

with open("requirements.txt", "r", encoding="utf-8") as fh:
    requirements = [line.strip() for line in fh if line.strip() and not line.startswith("#")]

setup(
    name="tendrl",
    version="0.1.7",
    author="Tendrl",
    author_email="support@tendrl.com",
    description="A Python SDK for the Tendrl data collection platform with cross-platform UNIX socket support, offline storage, and dynamic batching. Licensed for use with Tendrl services only.",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/tendrl-inc-labs/python-sdk",
    project_urls={
        "Bug Tracker": "https://github.com/tendrl-inc-labs/python-sdk/issues",
        "Documentation": "https://tendrl.com/docs/contact/sdks/python/getting-started/",
        "Source Code": "https://github.com/tendrl-inc-labs/python-sdk",
        "License": "https://github.com/tendrl-inc-labs/python-sdk/blob/main/LICENSE",
    },
    packages=find_packages(),
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Topic :: System :: Monitoring",
        "Topic :: System :: Logging",
        "Topic :: System :: Networking :: Monitoring",
        "Topic :: Internet",
        "License :: Other/Proprietary License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Operating System :: OS Independent",
        "Operating System :: Microsoft :: Windows :: Windows 10",
        "Operating System :: POSIX :: Linux",
        "Operating System :: MacOS",
    ],
    # 3.9 is the real floor: client.py imports zoneinfo, which is 3.9+. Declaring
    # 3.8 let `pip install tendrl` succeed and then fail on the first import —
    # the quick-start's very first line. 3.8 has been EOL since 2024-10.
    python_requires=">=3.9",
    install_requires=requirements,
    extras_require={
        "dev": [
            "pytest>=7.0",
            "pytest-asyncio>=0.21",
            "black>=22.0",
            "flake8>=4.0",
            "mypy>=1.0",
        ],
    },
    include_package_data=True,
    package_data={
        "tendrl": ["config.json"],
    },
    keywords="telemetry IoT monitoring data-collection agent sdk unix-socket batching offline-storage",
    zip_safe=False,
)
