#!/bin/bash

cd ../macos || exit
zip -r ../Releases/MacOS.zip nvfPostProcessor setup-postprocessor-macos.sh nvfPostprocessor.app
cd - || exit

cd ../windows || exit
zip -r ../Releases/Windows.zip nvfPostprocessor.exe setup-postprocessor-windows.bat create_shortcut.vbs
cd - || exit
