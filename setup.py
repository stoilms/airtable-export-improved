from setuptools import setup
import os

VERSION = "1.0"


def get_long_description():
    with open(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "README.md"),
        encoding="utf8",
    ) as fp:
        return fp.read()


setup(
    name="airtable-export",
    description="Export Airtable data to files on disk",
    long_description=get_long_description(),
    long_description_content_type="text/markdown",
    author="stoilms",
    url="https://github.com/stoilms/airtable-export-improved",
    project_urls={
        "Issues": "https://github.com/stoilms/airtable-export-improved/issues",
        "CI": "https://github.com/stoilms/airtable-export-improved/actions",
        "Changelog": "https://github.com/stoilms/airtable-export-improved/releases",
    },
    license="Apache License, Version 2.0",
    version=VERSION,
    packages=["airtable_export"],
    entry_points="""
        [console_scripts]
        airtable-export=airtable_export.cli:cli
    """,
    install_requires=[
        "click==8.5.1",
        "PyYAML==6.0.4",
        "httpx==0.28.1",
        "sqlite-utils==4.2.1",
        "openpyxl==3.1.5",
    ],
    extras_require={"test": ["pytest==9.2.0", "pytest-httpx==0.36.2"]},
)
