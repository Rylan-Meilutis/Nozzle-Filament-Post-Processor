#!/bin/bash
python3 -m venv venv
source venv/bin/activate

python -m pip install --upgrade pip
python -m pip install --upgrade -r requirements.txt
python version_file.py

venv/bin/pyinstaller --noconfirm --clean --onefile --noconsole --name "nvfPostprocessor" "nvfPostprocessor.py" -i="icon.png" --add-data "icon.png:." --version-file=version.ini

rm -rf build

mkdir -p ../linux
mv dist/nvfPostprocessor ../linux
rm -rf dist
rm version.ini

rm nvfPostprocessor.spec

deactivate
rm -rf venv