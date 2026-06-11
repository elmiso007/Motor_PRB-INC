@echo off
REM ==========================================================================
REM  Motor Prescritivo PRB - Validador de Entrega (prisma retrospectivo)
REM ==========================================================================
REM  Roda validar_entregas.py (sempre single-run).
REM  Agenda recomendada no Task Scheduler: a cada 6 horas.
REM
REM  Por que separado do Motor-PRB.bat:
REM    - O preventivo (main.py) roda rapido a cada 15 min.
REM    - O retrospectivo (validar_entregas) roda lento a cada 6h:
REM      PRB resolvido nao muda de hora em hora, e a query por PRB e mais cara.
REM    - Isolamento: se um bugar, nao derruba o outro.
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
"%VENV%\Scripts\python.exe" validar_entregas.py
set "EXITCODE=%ERRORLEVEL%"

endlocal & exit /b %EXITCODE%
