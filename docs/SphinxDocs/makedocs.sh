#!/bin/bash

# Assume Sphinx and the ReadTheDocs theme installed.
# Documentation placed in _build/html
#
# If not installed, run:
# pip3 install -r requirements.txt

# Auto-generate .rst files from docstrings for Python code in these folders.
sphinx-apidoc -f -o . ../../cloud_formation
sphinx-apidoc -f -o . ../../vault

# Generate HTML docs.
make html
