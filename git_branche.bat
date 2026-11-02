@echo off
chcp 65001 >nul
cd /d "%~dp0"
REM Cree le depot Git de TalentConnect et le publie sur GitHub (nouveau repo).
where git >nul 2>&1 || (echo Git introuvable : installez-le depuis https://git-scm.com puis relancez. & pause & exit /b 1)

if not exist .git git init -b main
git add -A
git commit -m "TalentConnect : suite de CVFlash (Flask + PostgreSQL)" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
REM Branche de travail demandee
git branch -f talentconnect >nul 2>&1

echo.
where gh >nul 2>&1
if %errorlevel%==0 (
  echo GitHub CLI detecte : creation du repo prive "talentconnect" sur votre compte...
  gh auth status >nul 2>&1 || gh auth login
  gh repo create talentconnect --private --source=. --remote=origin --push
  git push -u origin talentconnect
  echo.
  echo Termine. Repo en ligne : branches main et talentconnect.
  pause & exit /b 0
)

echo 1. Ouvrez https://github.com/new
echo 2. Nom du repo : talentconnect  (prive conseille, NE cochez PAS "Add a README")
echo 3. Cliquez "Create repository" puis copiez l'URL (https://github.com/VOTRE-COMPTE/talentconnect.git)
echo.
set /p REPO="Collez l'URL ici : "
if "%REPO%"=="" (echo Pas d'URL : depot local cree, rien n'a ete pousse. & pause & exit /b 0)
git remote remove origin >nul 2>&1
git remote add origin %REPO%
git push -u origin main
git push -u origin talentconnect
echo.
echo Termine. Repo en ligne : branches main et talentconnect.
pause
