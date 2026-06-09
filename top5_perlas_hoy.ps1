param(
    [string]$SymbolsFile = "data/pearl_symbols_ejemplo.txt",
    [double]$MinScore = 0.20,
    [int]$TopN = 5,
    [switch]$OnlineIOL,
    [switch]$NotifyTelegram,
    [switch]$JsonOnly,
    [switch]$WhatsApp,
    [switch]$WhatsAppArsOnly,
    [switch]$BymaUniverse,
    [int]$LimitCedears = 0,
    [int]$LimitEquities = 0,
    [switch]$ModoAmplio,
    [double]$MinMarketMovePct = 10.0
)

# Preset: más tickers BYMA, top 10, umbral más flexible, WhatsApp solo ARS.
# Los valores solo reemplazan defaults si no pasaste explícitamente ese parámetro.
if ($ModoAmplio) {
    if (-not $PSBoundParameters.ContainsKey("TopN")) { $TopN = 10 }
    if (-not $PSBoundParameters.ContainsKey("MinScore")) { $MinScore = 0.15 }
    if (-not $PSBoundParameters.ContainsKey("LimitCedears")) { $LimitCedears = 250 }
    if (-not $PSBoundParameters.ContainsKey("LimitEquities")) { $LimitEquities = 200 }
    $BymaUniverse = $true
    $WhatsAppArsOnly = $true
}

$argsList = @(
    "scripts/iol_top5_perlas_hoy.py",
    "--symbols-file", $SymbolsFile,
    "--min-score", "$MinScore",
    "--top-n", "$TopN",
    "--min-market-move-pct", ([string]([double]$MinMarketMovePct)).Replace(",", ".")
)
if ($ModoAmplio) {
    $argsList += @("--min-z", "0.60")
}

if (-not $OnlineIOL) {
    $argsList += "--offline"
}
if ($NotifyTelegram) {
    $argsList += "--notify-telegram"
}
if ($WhatsApp) {
    $argsList += "--print-whatsapp"
}
if ($WhatsAppArsOnly) {
    $argsList += @("--print-whatsapp", "--whatsapp-ars-only")
}
if ($BymaUniverse) {
    $argsList += "--use-byma-universe"
    if ($LimitCedears -gt 0) {
        $argsList += @("--limit-cedears", "$LimitCedears")
    }
    if ($LimitEquities -gt 0) {
        $argsList += @("--limit-equities", "$LimitEquities")
    }
}

if ($JsonOnly) {
    # En modo JsonOnly capturamos stdout+stderr, extraemos la última línea JSON
    # y emitimos SOLO ese bloque para permitir pipe directo a ConvertFrom-Json.
    $raw = python @argsList 2>&1
    if ($LASTEXITCODE -ne 0) {
        $raw | ForEach-Object { $_ }
        exit $LASTEXITCODE
    }
    $jsonLine = $raw | Where-Object {
        ($_ -is [string]) -and ($_.Trim().StartsWith("{")) -and ($_.Trim().EndsWith("}"))
    } | Select-Object -Last 1
    if (-not $jsonLine) {
        $raw | ForEach-Object { $_ }
        Write-Error "No se encontró JSON en la salida del proceso."
        exit 1
    }
    $jsonLine
    exit 0
}
else {
    Write-Host "Ejecutando Top $TopN perlas del dia..."
    if ($ModoAmplio) {
        Write-Host "Preset: MODO AMPLIO (BYMA amplio, min-score flexible, min-z 0.60, WhatsApp ARS)"
    }
    if ($OnlineIOL) {
        Write-Host "Modo: ONLINE IOL"
    }
    else {
        Write-Host "Modo: OFFLINE (Yahoo)"
    }
    python @argsList
}

