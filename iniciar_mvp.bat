@echo off
setlocal
cd /d "%~dp0"

rem El acceso directo llama al VBS para que nunca aparezca una consola.
rem Este archivo tambien puede ejecutarse directamente; la ventana se cierra enseguida.
if /i "%~1"=="--hidden" goto run_hidden

wscript.exe "%~dp0iniciar_swipeclean.vbs"
exit /b 0

:run_hidden
powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -WindowStyle Hidden -File "%~dp0scripts\start_swipeclean.ps1"
exit /b %errorlevel%
