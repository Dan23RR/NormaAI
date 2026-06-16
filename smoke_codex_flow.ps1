# NormaAI G6 Smoke Test - Codex download flow end-to-end.
# 1. Migra DB (alembic 006 - tracking columns)
# 2. Genera PDF aggiornato
# 3. Verifica backend test_leads still passes
# 4. Curl real-world: POST /leads + GET /codex/download

$ErrorActionPreference = 'Continue'

Write-Host ""
Write-Host "=== G6 Smoke: Codex download flow ===" -ForegroundColor Cyan
Write-Host "Timestamp: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
Write-Host ""

# Step 1: Alembic upgrade head (006)
Write-Host "Step 1: alembic upgrade head" -ForegroundColor Yellow
$alembic = poetry run alembic upgrade head 2>&1
$alembic | Select-Object -Last 4
if ($LASTEXITCODE -ne 0) {
    Write-Host "  AVVISO: alembic errori. Verifica DB." -ForegroundColor DarkYellow
}

# Step 2: Regenera PDF (con bookmarks + clickable links del round finale)
Write-Host ""
Write-Host "Step 2: rigenera PDF Codex (Python reportlab)" -ForegroundColor Yellow
poetry run python marketing/generate_pdf_native.py 2>&1 | Select-Object -Last 3
if (Test-Path "marketing/codex_post_omnibus_v1.pdf") {
    $pdfSize = [math]::Round((Get-Item "marketing/codex_post_omnibus_v1.pdf").Length / 1024, 1)
    Write-Host "  PDF: $pdfSize KB" -ForegroundColor Green
}

# Step 3: Pytest test_leads (sanity)
Write-Host ""
Write-Host "Step 3: pytest test_leads.py" -ForegroundColor Yellow
poetry run pytest tests/test_leads.py -v --tb=short --no-header 2>&1 | Select-Object -Last 5

# Step 4: Avvia uvicorn in foreground stack (lo lascia all'utente)
Write-Host ""
Write-Host "=== AZIONE MANUALE ===" -ForegroundColor Magenta
Write-Host "Apri 2 terminali PowerShell:" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Term 1 (backend):" -ForegroundColor Yellow
Write-Host "    cd $($PWD.Path)" -ForegroundColor Gray
Write-Host "    poetry run uvicorn src.api.main:app --host 127.0.0.1 --port 8000 --log-level info" -ForegroundColor Gray
Write-Host ""
Write-Host "  Term 2 (frontend):" -ForegroundColor Yellow
Write-Host "    cd $($PWD.Path)\frontend" -ForegroundColor Gray
Write-Host "    npm run dev" -ForegroundColor Gray
Write-Host ""

Write-Host "=== TEST END-TO-END (Term 3) ===" -ForegroundColor Magenta
Write-Host "Quando entrambi up, Term 3:" -ForegroundColor Cyan
Write-Host ""
Write-Host '  $body = @{ email = "test@example.com"; org_name = "Smoke Studio"; role = "Founder / Managing Partner"; source = "codex_download" } | ConvertTo-Json' -ForegroundColor Gray
Write-Host '  $r = Invoke-RestMethod -Uri http://127.0.0.1:8000/api/v1/leads -Method Post -ContentType "application/json" -Body $body' -ForegroundColor Gray
Write-Host '  $r' -ForegroundColor Gray
Write-Host ""
Write-Host "  # Atteso: download_url=/api/v1/codex/download?t=<UUID>.<exp>.<sig>" -ForegroundColor DarkGray
Write-Host ""
Write-Host '  $url = "http://127.0.0.1:8000$($r.download_url)"' -ForegroundColor Gray
Write-Host '  Invoke-WebRequest -Uri $url -OutFile downloaded_codex.pdf' -ForegroundColor Gray
Write-Host '  Get-Item downloaded_codex.pdf' -ForegroundColor Gray
Write-Host ""
Write-Host "  # Atteso: file ~50 KB salvato" -ForegroundColor DarkGray
Write-Host ""

Write-Host "=== TEST FRONTEND ===" -ForegroundColor Magenta
Write-Host "Apri http://localhost:3000/ -> compila form -> click 'Scarica il Codex'" -ForegroundColor Cyan
Write-Host "Atteso: card verde con button 'Scarica il Codex ora (PDF)' che apre il download." -ForegroundColor Cyan
Write-Host ""

Write-Host "=== EMAIL SMTP (opzionale) ===" -ForegroundColor Magenta
Write-Host "Per attivare invio email, aggiungi a .env:" -ForegroundColor Cyan
Write-Host "  SMTP_HOST=smtp.gmail.com" -ForegroundColor Gray
Write-Host "  SMTP_PORT=587" -ForegroundColor Gray
Write-Host "  SMTP_USER=info@normaai.org" -ForegroundColor Gray
Write-Host "  SMTP_PASSWORD=<gmail_app_password>     # crea su https://myaccount.google.com/apppasswords" -ForegroundColor Gray
Write-Host "  SMTP_FROM=info@normaai.org" -ForegroundColor Gray
Write-Host "  SMTP_USE_TLS=true" -ForegroundColor Gray
Write-Host "  APP_BASE_URL=http://localhost:8000     # in prod: https://normaai.it" -ForegroundColor Gray
Write-Host ""
Write-Host "Senza SMTP_*: i lead vengono comunque registrati e download_url e' funzionale." -ForegroundColor DarkGray
Write-Host "L'email invio fallisce silenziosamente con log warning, lead.email_error resta NULL." -ForegroundColor DarkGray
