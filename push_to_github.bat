@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo ========================================================
echo   🐹 倉鼠勇者 3.0 — 開發者一鍵清理・驗證・打包・上傳工具
echo ========================================================
echo.

echo [1/5] 🧹 正在清理本地暫存檔與 __pycache__...
python utils\cleaner.py
echo.

echo [2/5] 🔍 正在執行語法編譯檢查與核心測試...
python -m compileall -q main.py config.py build_update_pack.py utils cogs tests
if %ERRORLEVEL% neq 0 (
    echo ❌ 語法編譯檢查失敗！已中止上傳，請先修正錯誤。
    pause
    exit /b 1
)
python -m unittest discover -s tests
if %ERRORLEVEL% neq 0 (
    echo ❌ 單元測試未通過！已中止上傳，避免將異常代碼推上正式環境。
    pause
    exit /b 1
)
echo ✅ 語法與單元測試全數通過！
echo.

echo [3/5] 📦 正在產生最新 3.0 超輕量更新包 (update_pack.zip)...
python build_update_pack.py --no-clean
echo.

echo [4/5] 📋 目前變更清單 (git status):
git status -s
echo.

set /p COMMIT_MSG="請輸入 Commit 訊息 (直接按 Enter 自動套用預設訊息): "
if "%COMMIT_MSG%"=="" (
    for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyy-MM-dd_HH:mm"') do set NOW_TS=%%i
    set COMMIT_MSG=chore: 倉鼠勇者 3.0 更新與打包 (!NOW_TS!)
)

git add -A
git diff --cached --quiet
if %ERRORLEVEL% neq 0 (
    git commit -m "%COMMIT_MSG%"
) else (
    echo ℹ️ 無新的變更需要 commit，將直接推送現有提交...
)
echo.

echo [5/5] 🚀 正在推送至 GitHub (origin main)...
git push origin main
if %ERRORLEVEL% equ 0 (
    echo.
    echo ========================================================
    echo   ✅ 上傳成功！已同步至 GitHub 並備妥 update_pack.zip
    echo ========================================================
) else (
    echo.
    echo ========================================================
    echo   ❌ 上傳未完成，請確認網路連線或 GitHub 登入授權
    echo ========================================================
)
pause
