@echo off

pushd ..\macos
if errorlevel 1 exit /b
tar -a -c -f ..\Releases\MacOS.zip nvfPostProcessor setup-postprocessor-macos.sh nvfPostprocessor.app
popd

pushd ..\windows
if errorlevel 1 exit /b
tar -a -c -f ..\Releases\Windows.zip nvfPostprocessor.exe setup-postprocessor-windows.bat create_shortcut.vbs
popd