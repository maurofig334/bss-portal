# start_bss.ps1
# Sobe o ambiente BSS local de uma vez so:
#   1. Mata processos antigos (uvicorn + tunnel SSH)
#   2. Sobe tunnel SSH (porta local 15432 -> OCI:5432) em janela minimizada
#   3. Aguarda tunnel ficar pronto
#   4. Ativa venv e sobe uvicorn em foreground
#
# Uso:
#   .\start_bss.ps1
#
# Pra parar tudo: Ctrl+C aqui (mata uvicorn) + .\stop_bss.ps1 (mata tunnel)

# ===== Configuracao =====
$PROJETO      = Join-Path $PSScriptRoot "backend"
$CHAVE_SSH    = "C:\Users\mauro\Dropbox\Nexus\Adm\Oracle\nexus_openssh"
$OCI_HOST     = "opc@140.238.178.43"
$PORTA_LOCAL  = 15432
$PORTA_REMOTA = 5432
$PORTA_APP    = 8000

# ===== Helpers =====
function Get-PortPID($Porta) {
    return (Get-NetTCPConnection -LocalPort $Porta -State Listen -ErrorAction SilentlyContinue |
            Select-Object -First 1 -ExpandProperty OwningProcess)
}

function Kill-Port($Porta, $Rotulo) {
    $procId = Get-PortPID $Porta
    if ($procId) {
        Write-Host "  Matando $Rotulo (PID $procId, porta $Porta)..." -ForegroundColor Yellow
        Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
        Start-Sleep -Milliseconds 500
    }
}

# ===== 1. Limpar processos antigos =====
Write-Host "=== BSS - Limpando ambiente anterior ===" -ForegroundColor Cyan
Kill-Port $PORTA_APP   "uvicorn"
Kill-Port $PORTA_LOCAL "tunnel SSH"

# ===== 2. Verifica chave SSH =====
if (-not (Test-Path $CHAVE_SSH)) {
    Write-Host "ERRO: chave SSH nao encontrada em $CHAVE_SSH" -ForegroundColor Red
    exit 1
}

# ===== 3. Sobe tunnel SSH em janela minimizada =====
Write-Host "=== Subindo tunnel SSH ($OCI_HOST -> porta $PORTA_LOCAL) ===" -ForegroundColor Cyan
$argsSsh = @(
    "-N",
    "-L", "${PORTA_LOCAL}:localhost:${PORTA_REMOTA}",
    $OCI_HOST,
    "-i", $CHAVE_SSH,
    "-o", "ServerAliveInterval=60",
    "-o", "ExitOnForwardFailure=yes"
)
Start-Process -FilePath "ssh" -ArgumentList $argsSsh -WindowStyle Minimized

# ===== 4. Aguarda tunnel ficar pronto =====
Write-Host "  Aguardando tunnel..." -ForegroundColor Yellow
$tentativas = 0
do {
    Start-Sleep -Seconds 1
    $tentativas++
    $up = Test-NetConnection -ComputerName "localhost" -Port $PORTA_LOCAL -InformationLevel Quiet -WarningAction SilentlyContinue
} while (-not $up -and $tentativas -lt 10)

if (-not $up) {
    Write-Host "ERRO: tunnel nao subiu em 10s. Confira a chave e o IP." -ForegroundColor Red
    exit 1
}
Write-Host "  Tunnel pronto na porta $PORTA_LOCAL [OK]" -ForegroundColor Green

# ===== 5. Ativa venv e sobe uvicorn =====
Write-Host "=== Subindo uvicorn ===" -ForegroundColor Cyan
Set-Location $PROJETO

if (-not (Test-Path ".\venv\Scripts\Activate.ps1")) {
    Write-Host "ERRO: venv nao encontrada em $PROJETO\venv" -ForegroundColor Red
    Write-Host "Rode: python -m venv venv ; .\venv\Scripts\Activate.ps1 ; pip install -r requirements.txt" -ForegroundColor Yellow
    exit 1
}
& .\venv\Scripts\Activate.ps1

Write-Host ""
Write-Host "==============================================================" -ForegroundColor Cyan
Write-Host "  BSS - Beneficio Social Sindical" -ForegroundColor Cyan
Write-Host "  http://localhost:$PORTA_APP" -ForegroundColor Yellow
Write-Host "  Tunnel: localhost:$PORTA_LOCAL -> OCI:$PORTA_REMOTA" -ForegroundColor Gray
Write-Host "  Ctrl+C pra parar uvicorn (o tunnel fica vivo - rode stop_bss.ps1)" -ForegroundColor Gray
Write-Host "==============================================================" -ForegroundColor Cyan
Write-Host ""

uvicorn app.main:app --reload --port $PORTA_APP
