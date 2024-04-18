@echo off
setlocal enabledelayedexpansion

REM Create a virtual environment
python -m venv venv

REM Activate the virtual environment
call venv\Scripts\activate

REM Upgrade pip and install the requirements
python -m pip install --upgrade pip
python -m pip install --upgrade -r requirements.txt

REM Build the application
venv\Scripts\pyinstaller --noconfirm --onefile --noconsole --name "nvfPostprocessor" "nvfPostprocessor.py" -i="icon.png" --add-data "icon.png;."

REM Clean up
rmdir /s /q build
rmdir /s /q dist\nvfPostprocessor.app

REM Move the built application
if not exist ..\windows mkdir ..\windows
move dist\nvfPostprocessor ..\windows

REM More clean up
rmdir /s /q dist
del nvfPostprocessor.spec

REM Deactivate the virtual environment
call venv\Scripts\deactivate
rmdir /s /q venv