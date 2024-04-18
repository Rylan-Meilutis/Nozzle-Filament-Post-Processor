#!/bin/bash
python3 -m venv venv
source venv/bin/activate

python -m pip install --upgrade pip
python -m pip install --upgrade -r requirements.txt

venv/bin/pyinstaller --noconfirm --onefile --noconsole --name "nvfPostprocessor" "nvfPostprocessor.py" -i="icon.png" --add-data "icon.png:."

rm -rf build

mkdir -p ../linux
mv dist/nvfPostprocessor ../linux

rm -rf dist

rm nvfPostprocessor.spec

deactivate
rm -rf venv