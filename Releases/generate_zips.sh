#!/bin/bash

cd ../macos
zip -r ../Releases/MacOS.zip nvfPostProcessor setup-postprocessor-macos.sh nvfPostprocessor.app
cd -

cd ../windows
zip -r ../Releases/Windows.zip nvfPostprocessor.exe setup-postprocessor-windows.bat create_shortcut.vbs
cd -
