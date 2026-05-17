@echo off
setlocal

cd /d C:\Python\summarize_resume || goto :done
call .venv\Scripts\activate.bat

REM If ShareX passes a captured image, use it directly.
if not "%~1"=="" (
    set "input=%~1"
    goto :run
)

REM Without an argument, use the latest OCR PDF in the current ShareX month folder.
for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyy-MM"') do set "YM=%%i"
set "DIR=%USERPROFILE%\Documents\ShareX\Screenshots\%YM%"
echo DIR=%DIR%

for /f "delims=" %%i in ('dir "%DIR%\*.ocr.pdf" /b /a-d /o-d 2^>nul') do (
    set "input=%DIR%\%%i"
    goto :run
)

echo File not found: %DIR%\*.ocr.pdf
goto :done

:run
echo input=%input%

for %%F in ("%input%") do set "ext=%%~xF"

REM Images and non-OCR PDFs must go through OCR before summary/scout mail.
if /I not "%ext%"==".pdf" goto :run_ocr
if /I not "%input:~-8%"==".ocr.pdf" goto :run_ocr
goto :run_existing_ocr_pdf

:run_ocr
python ocr.py "%input%" --scout-mail
goto :done

:run_existing_ocr_pdf
python summarize_resume.py "%input%"
if errorlevel 1 goto :done
python scout_mail.py "%input%"
goto :done

:done
pause
