@echo off
REM Canli izleme - laptop modu. Cift tikla calistir; pencereyi acik birak.
REM Gerekli: Python 3 ve Git yuklu olsun, bu klasor repo klasoru olsun.
REM Slack uyarisi icin bir kere: setx SLACK_WEBHOOK_URL "https://hooks.slack.com/..."
cd /d "%~dp0"
:basla
python live_watch.py --loop --interval 60 --pull --push
echo Durdu, 15 sn sonra yeniden basliyor...
timeout /t 15 >nul
goto basla
