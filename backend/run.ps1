# Sobe o BSS localmente em http://localhost:8000
# Pre-requisito: venv ativada e dependencias instaladas.
#   python -m venv venv
#   .\venv\Scripts\Activate.ps1
#   pip install -r requirements.txt

Write-Host "==============================================================" -ForegroundColor Cyan
Write-Host "  BSS - Beneficio Social Sindical (DEV)" -ForegroundColor Cyan
Write-Host "  http://localhost:8000" -ForegroundColor Yellow
Write-Host "==============================================================" -ForegroundColor Cyan
Write-Host ""

uvicorn app.main:app --reload --port 8000
