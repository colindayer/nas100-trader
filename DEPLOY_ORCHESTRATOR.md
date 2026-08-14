# DEPLOY — one paste, then it runs itself

## 1. Pull everything
```powershell
$S="https://raw.githubusercontent.com/colindayer/nas100-trader/a02a21f"; foreach($f in "challenge_controller.py","desk_events.py","desk_orchestrator.py","market_state.py","desk.py","trading_brain.py","head_trader.py","bot_base.py"){iwr "$S/$f" -OutFile $f}
```

## 2. Verify (writes nothing to the market)
```powershell
py challenge_controller.py --dry-run; py desk_orchestrator.py
```
Expect `PREFLIGHT OK`, then `HEALTH GREEN/AMBER` and `DAILY_VALIDATION.md` written.

## 3. Schedule the orchestrator (every 15 min: health + evidence)
```powershell
$py = "C:\Users\Administrator\AppData\Local\Programs\Python\Python313\python.exe"; $act = New-ScheduledTaskAction -Execute $py -Argument "desk_orchestrator.py --sync" -WorkingDirectory "C:\Users\Administrator"; $trg = New-ScheduledTaskTrigger -Once -At (Get-Date).Date -RepetitionInterval (New-TimeSpan -Minutes 15) -RepetitionDuration (New-TimeSpan -Days 365); Register-ScheduledTask -TaskName "DeskOrchestrator" -Action $act -Trigger $trg -RunLevel Highest -Force
```

## 4. Make all three tasks survive a logoff (ops fix from OPERATIONS.md)
```powershell
foreach($n in "ChallengeController","HeadTraderReview","DeskOrchestrator"){ Set-ScheduledTask -TaskName $n -Principal (New-ScheduledTaskPrincipal -UserId "Administrator" -LogonType S4U -RunLevel Highest); $t=Get-ScheduledTask -TaskName $n; $t.Settings.DisallowStartIfOnBatteries=$false; $t.Settings.StopIfGoingOnBatteries=$false; Set-ScheduledTask -TaskName $n -Settings $t.Settings }
```

## 5. The one file to read
`DAILY_VALIDATION.md` — status, valid trades / 30, completeness table, no-trade codes,
and a single recommendation.
