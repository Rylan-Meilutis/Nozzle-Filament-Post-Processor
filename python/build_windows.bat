@echo off
setlocal enabledelayedexpansion

REM Create a virtual environment
python -m venv venv

REM Activate the virtual environment
call venv\Scripts\activate

REM Upgrade pip and install the requirements
python -m pip install --upgrade pip
python -m pip install --upgrade -r requirements.txt
python version_file.py

REM Build pyinstaller from source to reduce false positives from antivirus software
pip uninstall -y pyinstaller
git clone https://github.com/pyinstaller/pyinstaller
cd pyinstaller
git fetch --tags
for /f "delims=" %%i in ('git tag --sort=-creatordate') do set LATEST_TAG=%%i && goto :done
:done
git checkout %LATEST_TAG%
cd bootloader
python ./waf --gcc distclean all
cd ..
pip install .
cd ..
rmdir /s /q pyinstaller

REM Build the application
venv\Scripts\pyinstaller --noconfirm --clean --onefile --noconsole --name "nvfPostprocessor" "nvfPostprocessor.py" -i="icon.png" --add-data "icon.png;." --version-file=version.ini

REM Clean up
rmdir /s /q build

REM Move the built application
if not exist ..\windows mkdir ..\windows
move dist\nvfPostprocessor.exe ..\windows

REM More clean up
rmdir /s /q dist
del nvfPostprocessor.spec
del version.ini
REM Deactivate the virtual environment
call venv\Scripts\deactivate
rmdir /s /q venv