@echo off
chcp 65001 >nul
title TalentConnect
cd /d "%~dp0"

if not exist venv (
  echo [1/3] Creation de l'environnement Python...
  python -m venv venv || (echo Python introuvable. Installez Python 3.11+ depuis python.org & pause & exit /b 1)
)
call venv\Scripts\activate

echo [2/3] Installation des dependances...
python -m pip install --upgrade pip >nul
pip install -r requirements.txt

if not exist .env (
  copy .env.example .env >nul
  echo Fichier .env cree : pensez a le completer (PostgreSQL, Brevo, cle IA).
)

echo [3/3] Lancement sur http://localhost:5000
start "" http://localhost:5000
python run.py
pause
