@echo off
IF NOT EXIST data.json echo. > data.json
IF NOT EXIST nfvsettings.json echo. > nfvsettings.json

cscript //nologo create_shortcut.vbs "%cd%\nvfPostprocessor.exe"
echo Postprocessor setup complete.
echo.
echo Enter the following in your slicers post processor section:
echo.
echo %cd%\nvfPostprocessor.exe
