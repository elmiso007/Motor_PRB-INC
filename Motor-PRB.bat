@echo off
REM ==========================================================================
REM  Motor Prescritivo PRB - wrapper para Windows Task Scheduler
REM ==========================================================================
REM  Roda main.py (prisma preventivo, sempre single-run).
REM  Agenda recomendada no Task Scheduler: a cada 15 minutos.
REM
REM  Caminhos absolutos para funcionar independente do working directory
REM  passado pelo Task Scheduler.
REM ==========================================================================
setlocal

REM Pasta raiz do projeto = pasta deste .bat
set "PROJ=%~dp0"

REM venv compartilhado com locapredict (1 nivel acima do projeto)
set "VENV=C:\Users\emerson.ramos\Desktop\projetos\.venv"

REM Producao usa banco real (sem mocks)
set "USAR_MOCKS=false"

REM Garante working dir certo (logs vao gravar em .\logs)
cd /d "%PROJ%"

REM Executa
"%VENV%\Scripts\python.exe" main.py
set "EXITCODE=%ERRORLEVEL%"

endlocal & exit /b %EXITCODE%