@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo 正在推送最新代碼至 GitHub (alebc347-wq/mch-BR20-dwgd8gd4g8d1gd874s18gd-jkl-iu8y-)...
git push origin main
if %ERRORLEVEL% equ 0 (
    echo.
    echo ========================================
    echo   ✅ 成功上傳至 GitHub！
    echo ========================================
) else (
    echo.
    echo ========================================
    echo   ❌ 上傳未完成，請確認 GitHub 驗證視窗或登入授權
    echo ========================================
)
pause
