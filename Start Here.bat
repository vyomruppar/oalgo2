@echo off
setlocal
title oalgo2 Observatory
cd /d "%~dp0"

rem Opened straight from a ZIP, Windows runs it from a temporary folder where nothing can be saved.
echo "%~dp0" | findstr /i /c:"\AppData\Local\Temp\" >nul
if not errorlevel 1 goto :zipped

echo.
echo   oalgo2 Observatory
echo   ------------------
echo.

rem uv sets up Python and everything else. Install it once if it is not here yet.
set "UV=uv"
where uv >nul 2>nul
if not errorlevel 1 goto :haveuv
set "UV=%USERPROFILE%\.local\bin\uv.exe"
if exist "%UV%" goto :haveuv
echo   Installing uv, which sets up Python for oalgo2. First start only.
powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/0.11.32/install.ps1 | iex"
if not exist "%UV%" goto :fail

:haveuv
echo   Getting everything ready. The first start downloads about 2 GB
echo   and can take 10 minutes. Later starts take a few seconds.
echo.

rem Keep this file small and unchanging: updates never replace it, because it is the file running them.
rem Exit code 75 = oalgo2 asked to install a downloaded update, then start again.
rem Exit code 76 = the updated version would not start, so go back to the previous one.
:run
if not exist "data\updates\pending.json" goto :start
copy /y "launcher\apply_update.py" "%TEMP%\oalgo2_apply.py" >nul
"%UV%" run --no-project --python 3.13 "%TEMP%\oalgo2_apply.py" "%CD%"

:start
"%UV%" run --project backend --frozen --no-dev --group ai --group desktop python launcher\launch.py %*
set "CODE=%errorlevel%"
if "%CODE%"=="75" goto :run
if "%CODE%"=="76" goto :rollback
if not "%CODE%"=="0" goto :fail
exit /b 0

:rollback
copy /y "launcher\apply_update.py" "%TEMP%\oalgo2_apply.py" >nul
"%UV%" run --no-project --python 3.13 "%TEMP%\oalgo2_apply.py" "%CD%" rollback
goto :start

:zipped
echo.
echo   Please extract the ZIP first: right-click the downloaded ZIP file,
echo   choose "Extract All", then open "Start Here" inside the extracted folder.
echo.
pause
exit /b 1

:fail
echo.
echo   oalgo2 did not start. The message above says why.
echo   Press any key to close this window.
pause >nul
exit /b 1
