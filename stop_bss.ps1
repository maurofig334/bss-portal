# stop_bss.ps1
# Para todos os processos do ambiente BSS local:
#   - uvicorn (porta 8000)
#   - tunnel SSH (porta 15432)
#
# Uso:  .\stop_bss.ps1

$PORTA_LOCAL = 15432
$PORTA_APP   = 8000

function Get-PortPID($Porta) {
    return (Get-NetTCPConnection -LocalPort $Porta -State Listen -ErrorAction SilentlyContinue |
            Select-Object -First 1 -ExpandProperty OwningProcess)
}

function Kill-Port($Porta, $Rotulo) {
    $procId = Get-PortPID $Porta
    if ($procId) {
        Write-Host "Matando $Rotulo (PID $procId, porta $Porta)..." -ForegroundColor Yellow
        Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
        Write-Host "  [OK]" -ForegroundColor Green
    } else {
        Write-Host "$Rotulo: nao esta rodando (porta $Porta)" -ForegroundColor Gray
    }
}

Write-Host "=== Parando ambiente BSS ===" -ForegroundColor Cyan
Kill-Port $PORTA_APP   "uvicorn"
Kill-Port $PORTA_LOCAL "tunnel SSH"
Write-Host "Pronto." -ForegroundColor Green
