@echo off
chcp 65001 >nul
echo ================================================
echo   YouTube 頻道分析工具啟動中...
echo ================================================
echo.

REM 檢查 Ollama 是否在運行
echo [1/3] 檢查 Ollama 服務...
tasklist /FI "IMAGENAME eq ollama.exe" 2>NUL | find /I /N "ollama.exe">NUL
if "%ERRORLEVEL%"=="1" (
    echo       Ollama 未運行,正在啟動...
    start /B ollama serve
    timeout /t 3 /nobreak >nul
    echo       Ollama 已啟動
) else (
    echo       Ollama 已在運行
)

echo.
echo [2/3] 啟動 Flask 後端服務...
start /B python server.py
timeout /t 3 /nobreak >nul
echo       Flask 服務已啟動

echo.
echo [3/3] 開啟瀏覽器...
start http://localhost:5000
echo       瀏覽器已開啟

echo.
echo ================================================
echo   所有服務已啟動完成!
echo   瀏覽器應該已自動開啟 http://localhost:5000
echo   
echo   關閉此視窗將停止所有服務
echo ================================================
pause