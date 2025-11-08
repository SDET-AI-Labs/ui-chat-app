# -*- coding: utf-8 -*-
from setuptools import setup, find_packages

setup(
    name="chatstack",
    version="0.1.0",
    packages=find_packages("src"),
    package_dir={"": "src"},
    python_requires=">=3.10",
    install_requires=[
        "fastapi>=0.110",
        "uvicorn[standard]>=0.29",
        "httpx>=0.27",
        "pydantic>=2.5",
        "pydantic-settings>=2.2",
        "sse-starlette>=2.0",
        "Pillow>=10.0",
        "python-dotenv>=1.0",
        "openpyxl>=3.1",
        "requests>=2.31",
        "playwright>=1.40",
    ],
    extras_require={
        "dev": [
            "pytest>=7.0",
            "pytest-asyncio>=0.21",
            "black>=23.0",
            "pylint>=2.17",
            "mypy>=1.5",
        ]
    },
    entry_points={
        "console_scripts": [
            "chatstack=chatstack.cli_chat:main",
        ]
    },
    author="ChatStack Maintainers",
    description="Pluggable Python chat service with FastAPI and multiple LLM backends",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    license="MIT",
    keywords="chat ai llm fastapi testing",
    project_urls={
        "Source": "https://github.com/SDET-AI-Labs/ui-chat-app",
    },
)