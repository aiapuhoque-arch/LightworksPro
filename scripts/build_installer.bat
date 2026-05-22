@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0.."

echo ============================================================
echo  Lightworks Pro — Windows Installer Build
echo ============================================================
echo.

:: ----------------------------------------------------------------
:: 1. Python check
:: ----------------------------------------------------------------
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Install Python 3.12+ from python.org
    goto :fail
)
for /f "tokens=2" %%v in ('python --version 2^>^&1') do set PY_VER=%%v
echo [OK] Python %PY_VER%

:: ----------------------------------------------------------------
:: 2. Install / upgrade build dependencies
:: ----------------------------------------------------------------
echo.
echo [STEP 1/4] Installing build dependencies...
pip install --upgrade pyinstaller pyinstaller-hooks-contrib >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Failed to install PyInstaller
    goto :fail
)
python -m PyInstaller --version >nul 2>&1
if errorlevel 1 ( echo [ERROR] PyInstaller not importable & goto :fail )
echo [OK] PyInstaller ready

:: ----------------------------------------------------------------
:: 3. Generate icon (idempotent — skip if already exists)
:: ----------------------------------------------------------------
if not exist "assets\lightworks_pro.ico" (
    echo.
    echo [STEP 2/4] Generating application icon...
    python -c "
from PIL import Image, ImageDraw; import os; os.makedirs('assets',exist_ok=True)
def f(s):
    img=Image.new('RGBA',(s,s),(0,0,0,0)); d=ImageDraw.Draw(img)
    p=s//8; d.ellipse([p,p,s-p,s-p],fill=(0,85,184,255))
    r=s//10; d.ellipse([p+r,p+r,s-p-r,s-p-r],outline=(255,255,255,200),width=max(1,s//24))
    cx=s//2; mw=s//8; mh=s//4; mt=s//3
    d.rounded_rectangle([cx-mw,mt,cx+mw,mt+mh],radius=mw,fill=(255,255,255,255))
    ar=s//5; at=mt+mh-s//16
    d.arc([cx-ar,at,cx+ar,at+ar],start=0,end=180,fill=(255,255,255,220),width=max(1,s//20))
    pw=max(1,s//24); d.rectangle([cx-pw,at+ar//2,cx+pw,at+ar//2+s//10],fill=(255,255,255,220))
    return img
sizes=[16,24,32,48,64,128,256]; frames=[f(s) for s in sizes]
frames[0].save('assets/lightworks_pro.ico',format='ICO',sizes=[(s,s) for s in sizes],append_images=frames[1:])
print('Icon generated')
"
    if errorlevel 1 ( echo [ERROR] Icon generation failed & goto :fail )
    echo [OK] Icon generated
) else (
    echo [STEP 2/4] Icon already exists — skipping
)

:: ----------------------------------------------------------------
:: 4. PyInstaller bundle
:: ----------------------------------------------------------------
echo.
echo [STEP 3/4] Building with PyInstaller (this takes 1-3 minutes)...
if exist "dist\LightworksPro" rmdir /s /q "dist\LightworksPro"
if exist "build\_pyinstaller"  rmdir /s /q "build\_pyinstaller"

python -m PyInstaller build\lightworks_pro.spec ^
    --distpath dist ^
    --workpath build\_pyinstaller ^
    --noconfirm ^
    --clean

if errorlevel 1 (
    echo [ERROR] PyInstaller failed. Check build\_pyinstaller\warn-LightworksPro.txt
    goto :fail
)

if not exist "dist\LightworksPro\LightworksPro.exe" (
    echo [ERROR] EXE not found after PyInstaller run
    goto :fail
)
echo [OK] Bundle created: dist\LightworksPro\LightworksPro.exe

:: ----------------------------------------------------------------
:: 5. Inno Setup  (optional — skip gracefully if not installed)
:: ----------------------------------------------------------------
echo.
echo [STEP 4/4] Creating installer with Inno Setup...

set ISCC=
for %%p in (
    "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
    "%ProgramFiles%\Inno Setup 6\ISCC.exe"
    "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
    "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
) do (
    if exist %%p set ISCC=%%p
)

if "!ISCC!"=="" (
    echo [WARN] Inno Setup not found. Install from https://jrsoftware.org/isdl.php
    echo        Then run:  "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer\setup.iss
    echo.
    echo [DONE] PyInstaller bundle is ready in dist\LightworksPro\
    echo        You can run it directly: dist\LightworksPro\LightworksPro.exe
    goto :success
)

mkdir "dist\installer" 2>nul
!ISCC! installer\setup.iss
if errorlevel 1 (
    echo [ERROR] Inno Setup compilation failed
    goto :fail
)

echo.
echo ============================================================
echo  BUILD COMPLETE
echo  Installer: dist\installer\LightworksPro_Setup_1.2.0.exe
echo ============================================================
goto :success

:fail
echo.
echo [BUILD FAILED]
endlocal
exit /b 1

:success
endlocal
exit /b 0
