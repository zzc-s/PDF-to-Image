@echo off
cd /d "%~dp0"

python --version >nul 2>&1
if not errorlevel 1 goto run_python

py -3 --version >nul 2>&1
if not errorlevel 1 goto run_py3

"C:\Users\Lenovo\AppData\Local\Programs\Python\Python312\python.exe" --version >nul 2>&1
if not errorlevel 1 goto run_py312

echo Python 未找到，请先安装 Python 3.10 或更高版本。
pause
exit /b 1

:run_python
python -m pip install -r requirements.txt -q
python app.py
goto end

:run_py3
py -3 -m pip install -r requirements.txt -q
py -3 app.py
goto end

:run_py312
"C:\Users\Lenovo\AppData\Local\Programs\Python\Python312\python.exe" -m pip install -r requirements.txt -q
"C:\Users\Lenovo\AppData\Local\Programs\Python\Python312\python.exe" app.py
goto end

:end
pause
