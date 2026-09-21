@echo off
title Painel de Investimentos
cd /d "%~dp0"

if not exist ".venv\Scripts\streamlit.exe" (
    echo Primeira execucao: instalando o ambiente, aguarde...
    python -m venv .venv
    ".venv\Scripts\python.exe" -m pip install --upgrade pip
    ".venv\Scripts\pip.exe" install -r requirements.txt
)

echo.
echo Abrindo o Painel de Investimentos no navegador...
echo Para encerrar, feche esta janela preta.
echo.
".venv\Scripts\streamlit.exe" run app.py
pause