import os
from setuptools import setup, find_packages

# Read imports from requirements.txt if possible, or just list standard ones here
# For a setup.py, it's often cleaner to list main dependencies directly or read the file.
# I'll list them directly for simplicity in the package definition.

setup(
    name="net-diag-tool",
    version="1.0.0",
    description="A production-ready IT Operations Diagnostic Suite",
    author="Nurwell",
    author_email="", # Set your email
    package_dir={"": "src"},
    packages=find_packages(where="src"),
    install_requires=[
        "typer>=0.9.0",
        "rich>=13.0.0",
        "psutil>=5.9.0",
        "requests>=2.31.0",
        "pydantic>=2.0.0",
        "pydantic-settings>=2.0.0",
        "jinja2>=3.1.0",
        "python-dotenv>=1.0.0",
    ],
    extras_require={
        "dev": [
            "pytest>=7.0.0",
            "pytest-cov>=4.0.0",
            "black>=23.0.0",
            "mypy>=1.0.0",
            "isort>=5.0.0",
        ]
    },
    entry_points={
        "console_scripts": [
            "netdiag=net_diag_tool.main:app",
        ],
    },
    python_requires=">=3.9",
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Intended Audience :: System Administrators",
        "Programming Language :: Python :: 3",
        "Operating System :: OS Independent",
    ],
)
