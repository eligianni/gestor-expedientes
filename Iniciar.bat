@echo off
rem Gestor de expedientes de pago - doble clic para abrir
cd /d "%~dp0"
where pythonw >nul 2>nul && (start "" /b pythonw app.py & exit /b 0)
where pyw >nul 2>nul && (start "" /b pyw -3 app.py & exit /b 0)
where py >nul 2>nul && (start "" /b py -3 app.py & exit /b 0)
echo No se encontro Python 3.10 o superior en esta PC.
echo Instalarlo desde https://www.python.org/downloads/windows/ marcando "Add python.exe to PATH" y volver a hacer doble clic.
pause
exit /b 1
