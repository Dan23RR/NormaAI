# Genera codex_post_omnibus_v1.pdf usando Edge/Chrome headless.
# Pre-req: Next.js dev server up su :3000 (per servire codex.html con hot reload).
# ASCII-only.

$ErrorActionPreference = 'Continue'

Write-Host ""
Write-Host "=== Generazione Codex Post-Omnibus PDF (v2) ===" -ForegroundColor Cyan

# Step 1: refresh frontend public dir copy (in caso di update marketing/*.html)
Write-Host "Step 1: sync marketing/codex_post_omnibus.html -> frontend/public/codex.html" -ForegroundColor Yellow
Copy-Item ".\marketing\codex_post_omnibus.html" ".\frontend\public\codex.html" -Force
Write-Host "  Sync OK ($([math]::Round((Get-Item .\frontend\public\codex.html).Length/1024,1)) KB)" -ForegroundColor Green

# Step 2: verifica che il file sia accessibile su localhost
$url = "http://localhost:3000/codex.html"
Write-Host ""
Write-Host "Step 2: verifica $url" -ForegroundColor Yellow
try {
    $resp = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 5
    if ($resp.StatusCode -ne 200) { throw "HTTP $($resp.StatusCode)" }
    Write-Host "  OK ($([math]::Round($resp.Content.Length/1024,1)) KB)" -ForegroundColor Green
} catch {
    Write-Host "  ERRORE: $url non reachable. Avvia frontend con: cd frontend && npm run dev" -ForegroundColor Red
    Write-Host "  Fallback: aprire codex_post_omnibus.html in Chrome -> Ctrl+P -> Save as PDF" -ForegroundColor Yellow
    exit 1
}

# Step 3: trova un browser headless (Edge primario, Chrome fallback)
$candidates = @(
    "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe",
    "${env:ProgramFiles}\Microsoft\Edge\Application\msedge.exe",
    "${env:ProgramFiles}\Google\Chrome\Application\chrome.exe",
    "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe",
    "${env:LOCALAPPDATA}\Google\Chrome\Application\chrome.exe"
)
$browser = $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $browser) {
    Write-Host "  ERRORE: nessun browser headless trovato. Apri manualmente codex.html e Ctrl+P -> Save as PDF." -ForegroundColor Red
    exit 1
}
Write-Host ""
Write-Host "Step 3: browser trovato: $browser" -ForegroundColor Green

# Step 4: print-to-PDF con flag tuning per documento lungo
$outputPath = (Resolve-Path .).Path + "\marketing\codex_post_omnibus_v1.pdf"
Write-Host ""
Write-Host "Step 4: print-to-PDF" -ForegroundColor Yellow
Write-Host "  Output: $outputPath"
Write-Host "  Virtual time budget: 60s (consente caricamento Google Fonts + render lungo)"

# Rimuovi PDF precedente
if (Test-Path $outputPath) { Remove-Item $outputPath -Force }

$args = @(
    "--headless=new",
    "--disable-gpu",
    "--no-sandbox",
    "--print-to-pdf=$outputPath",
    "--no-pdf-header-footer",
    # virtual-time-budget = budget di tempo simulato in ms (Chrome avanza il tempo virtualmente).
    # 60000 = 60s simulati; necessario per documenti lunghi con webfonts esterni.
    "--virtual-time-budget=60000",
    "--run-all-compositor-stages-before-draw",
    "--disable-features=PaintHolding",
    # White page background: the codex is a light "warm paper" document; a black
    # default made every non-painted margin/gap render black in the PDF.
    "--default-background-color=ffffff",
    $url
)

Write-Host "  Lancio: $browser $($args -join ' ')" -ForegroundColor Gray
& $browser @args 2>&1 | Out-Null

# Step 5: verifica output
Start-Sleep -Seconds 3
if (Test-Path $outputPath) {
    $pdf = Get-Item $outputPath
    $sizeKB = [math]::Round($pdf.Length / 1024, 1)
    Write-Host ""
    Write-Host "  PDF generato: $sizeKB KB" -ForegroundColor Green
    Write-Host "  Path: $outputPath" -ForegroundColor Green

    # Conta pagine via shell PDF metadata se disponibile (best effort)
    try {
        $pdfBytes = [System.IO.File]::ReadAllText($outputPath, [System.Text.Encoding]::ASCII)
        $pageCount = ([regex]::Matches($pdfBytes, '/Type\s*/Page[^s]')).Count
        if ($pageCount -gt 0) {
            Write-Host "  Pagine stimate: $pageCount" -ForegroundColor Cyan
            if ($pageCount -lt 14) {
                Write-Host "  AVVISO: il PDF potrebbe essere troncato. Atteso 18-22 pp." -ForegroundColor Yellow
                Write-Host "  Workaround: prova FALLBACK manuale (vedi sotto)." -ForegroundColor Yellow
            } else {
                Write-Host "  OK: count pagine plausibile." -ForegroundColor Green
            }
        }
    } catch {
        Write-Host "  (Non posso contare le pagine: $($_.Exception.Message))" -ForegroundColor Gray
    }

    Write-Host ""
    Write-Host "Apri con: start `"`" `"$outputPath`"" -ForegroundColor Cyan
} else {
    Write-Host ""
    Write-Host "  PDF NON generato." -ForegroundColor Red
    Write-Host ""
    Write-Host "FALLBACK manuale (sempre funziona):" -ForegroundColor Yellow
    Write-Host "  1. Apri Chrome o Edge -> $url" -ForegroundColor Yellow
    Write-Host "  2. Ctrl+P (stampa)" -ForegroundColor Yellow
    Write-Host "  3. Destinazione: 'Save as PDF'" -ForegroundColor Yellow
    Write-Host "  4. Margini: Default. Layout: Verticale. Sfondi grafici: ON." -ForegroundColor Yellow
    Write-Host "  5. Salva come: marketing\codex_post_omnibus_v1.pdf" -ForegroundColor Yellow
}
