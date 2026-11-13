@echo off
REM Canli izleme kurulumu (Windows). Cift tikla calistir. Tekrar calistirmak zararsizdir.
REM Yaptiklari: Python ve Git yoksa kurar (winget), repoyu Belgeler'e indirir, GitHub girisini yaptirir,
REM Slack webhook adresini sorar. Sonunda laptop_canli.bat'i baslatmak sana kalir.
setlocal
set "HEDEF=%USERPROFILE%\Documents\Football-ChatGPT-decision-"
set EKSIK=0

python --version >nul 2>&1
if errorlevel 1 (
  echo [1/4] Python kuruluyor...
  winget install -e --id Python.Python.3.12 --accept-source-agreements --accept-package-agreements
  set EKSIK=1
) else (
  echo [1/4] Python var.
)

git --version >nul 2>&1
if errorlevel 1 (
  echo [2/4] Git kuruluyor... (Windows izin sorarsa Evet de)
  winget install -e --id Git.Git --accept-source-agreements --accept-package-agreements
  set EKSIK=1
) else (
  echo [2/4] Git var.
)

if "%EKSIK%"=="1" (
  echo.
  echo Kurulum yapildi. Bu pencereyi kapat ve kurulum_canli.bat dosyasina BIR KEZ DAHA cift tikla.
  pause
  exit /b
)

if exist "%HEDEF%\.git" (
  echo [3/4] Repo zaten var, guncelleniyor...
  git -C "%HEDEF%" pull --rebase --autostash -q
) else (
  echo [3/4] Repo indiriliyor...
  git clone https://github.com/nadogus/Football-ChatGPT-decision- "%HEDEF%"
)
if not exist "%HEDEF%\live_watch.py" (
  echo HATA: repo indirilemedi. Interneti kontrol edip tekrar dene.
  pause
  exit /b 1
)
git -C "%HEDEF%" config user.name >nul 2>&1 || git -C "%HEDEF%" config user.name "laptop"
git -C "%HEDEF%" config user.email >nul 2>&1 || git -C "%HEDEF%" config user.email "laptop@users.noreply.github.com"
echo GitHub girisi kontrol ediliyor (tarayici acilirsa GitHub hesabinla giris yap)...
git -C "%HEDEF%" push --dry-run
if errorlevel 1 echo UYARI: GitHub girisi tamamlanmadi. Bu dosyayi tekrar calistirip giris yap.

echo.
echo [4/4] Slack webhook adresi (https://hooks.slack.com/... ile baslar).
echo Yapistirip Enter'a bas. Simdilik gecmek icin bos birakip Enter'a bas.
set "HOOK="
set /p HOOK=Adres: 
if not "%HOOK%"=="" (
  setx SLACK_WEBHOOK_URL "%HOOK%" >nul
  echo Slack adresi kaydedildi.
) else (
  echo Slack adresi girilmedi; veri toplanir ama uyari gitmez.
)

echo.
echo Kurulum tamam. Baslatmak icin su dosyaya cift tikla:
echo   %HEDEF%\laptop_canli.bat
explorer "%HEDEF%"
pause
