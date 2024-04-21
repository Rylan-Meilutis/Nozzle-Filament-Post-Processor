#!/bin/bash
python3 -m venv venv
source venv/bin/activate

python -m pip install --upgrade pip
python -m pip install --upgrade -r requirements.txt

venv/bin/pyinstaller --noconfirm --clean --onefile --noconsole --name "nvfPostprocessor" "nvfPostprocessor.py" -i="icon.png" --add-data "icon.png:." --version-file=version.ini

rm -rf build
rm -rf dist/nvfPostprocessor.app/Contents/MacOS/nvfPostprocessor
rm -rf ../macos/nvfPostprocessor.app/

mkdir -p ../macos
mv dist/nvfPostprocessor ../macos
mv dist/nvfPostprocessor.app ../macos
rm -rf dist

rm nvfPostprocessor.spec

deactivate
rm -rf venv