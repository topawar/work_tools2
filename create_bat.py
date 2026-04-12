# -*- coding: utf-8 -*-
"""
创建正确编码的批处理文件
"""

content = """@echo off
setlocal enabledelayedexpansion

echo ========================================
echo Work Tools Build Script
echo ========================================
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found
    pause
    exit /b 1
)

echo [Step 1/4] Checking Python...
python --version
echo.

echo [Step 2/4] Installing PyInstaller...
pip install pyinstaller -q
echo.

echo [Step 3/4] Generating requirements.txt...
if not exist "requirements.txt" (
    pip freeze > requirements.txt
    echo Generated requirements.txt
) else (
    echo requirements.txt exists
)
echo.

echo [Step 4/4] Building...
echo This may take a few minutes...
echo.

pyinstaller --clean --noconfirm --onedir --name "WorkTools" --add-data "templates;templates" --add-data "static;static" --add-data "work_tools2;work_tools2" --add-data "manage.py;." --hidden-import=django --hidden-import=pypinyin --hidden-import=sqlite3 --collect-all django --console launcher.py

if errorlevel 1 (
    echo.
    echo [ERROR] Build failed!
    pause
    exit /b 1
)

echo.
echo ========================================
echo Build Completed!
echo ========================================
echo.

if exist "db.sqlite3" (
    copy /Y "db.sqlite3" "dist\\WorkTools\\" >nul
    echo [OK] Database copied
)

if exist "\\xe4\\xbd\\xbf\\xe7\\x94\\xa8\\xe8\\xaf\\xb4\\xe6\\x98\\x8e.txt" (
    copy /Y "\\xe4\\xbd\\xbf\\xe7\\x94\\xa8\\xe8\\xaf\\xb4\\xe6\\x98\\x8e.txt" "dist\\WorkTools\\" >nul
    echo [OK] README copied
)

echo Output: %CD%\\dist\\WorkTools
echo.
echo How to use:
echo 1. Copy WorkTools folder to target PC
echo 2. Double-click WorkTools.exe
echo 3. Browser opens at http://127.0.0.1:9123
echo.
pause
"""

# 使用GBK编码写入文件（Windows批处理文件标准编码）
with open('build_simple.bat', 'w', encoding='gbk') as f:
    f.write(content)

print("build_simple.bat created successfully with GBK encoding")
