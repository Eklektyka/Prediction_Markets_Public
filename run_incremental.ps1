# run_incremental.ps1 — one incremental Kalshi collection pass (called by Task Scheduler).
# Runs the collector using the venv's python, with the correct series list.

Set-Location "C:\Users\micha\OneDrive\Pulpit\Kalshi\Prediction_Markets_Public"

# canonical research series: 6 macro + the correct UFC fight series
$env:SERIES = 'KXUFCFIGHT,KXFED,KXFEDDECISION,KXCPIYOY,KXCPICOREYOY,KXPAYROLLS,KXU3'

# use the venv python directly (no activation needed)
& ".\.venv\Scripts\python.exe" "kalshi_forward_collector.py"
