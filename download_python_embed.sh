#!/bin/bash
# Script to download Python embeddable package for Windows

echo "Downloading Python 3.11 embeddable package for Windows (64-bit)..."
curl -L -o python-embed.zip "https://www.python.org/ftp/python/3.11.9/python-3.11.9-embed-amd64.zip"

echo "Extracting Python..."
mkdir -p python
cd python
unzip ../python-embed.zip
cd ..

echo "Setting up pip in embedded Python..."
curl -L -o get-pip.py "https://bootstrap.pypa.io/get-pip.py"

echo "Python embeddable package downloaded successfully!"
echo "Note: On Windows, you'll need to run: python\\python.exe get-pip.py"
echo "Then install packages: python\\python.exe -m pip install pynetdicom pydicom pyyaml"