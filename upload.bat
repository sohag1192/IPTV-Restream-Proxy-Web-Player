@echo off
cd /d "D:\My_Project\Restream"

IF NOT EXIST .git (
    git init
    git branch -M main
    git remote add origin https://github.com/sohag1192/IPTV-Restream-Proxy-Web-Player.git
)

echo Adding all files...
git add .

echo Pulling latest changes from GitHub...
git pull --rebase origin main

set /p msg="Enter commit message (or press Enter for default): "
if "%msg%"=="" set msg=Update IPTV Restream Suite

git commit -m "%msg%"

echo Pushing to GitHub (this triggers auto release)...
git push -u origin main

echo.
echo ========================================================
echo   Pushed successfully! Auto-release workflow triggered.
echo ========================================================
pause
