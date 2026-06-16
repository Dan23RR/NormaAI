# NormaAI - Test Suite Runner (G1.2)
# Pre-req: Python 3.11+, Poetry (https://python-poetry.org), Docker Desktop
# Esegui in PowerShell dalla cartella normaai/

$ErrorActionPreference = 'Continue'  # vogliamo vedere TUTTI i fallimenti

Write-Host "=== NormaAI Test Run ===" -ForegroundColor Cyan
Write-Host "Timestamp: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')`n"

# 0. Verifica strumenti
Write-Host "Step 0: tooling check" -ForegroundColor Yellow
$pyver = python --version 2>&1
Write-Host "  python: $pyver"
$poetryver = poetry --version 2>&1
Write-Host "  poetry: $poetryver"
$dockerver = docker --version 2>&1
Write-Host "  docker: $dockerver"

# 1. Install deps (idempotente)
Write-Host "`nStep 1: poetry install (potrebbe richiedere 3-5 min la prima volta)" -ForegroundColor Yellow
poetry install --no-interaction 2>&1 | Tee-Object -FilePath ".pytest_install.log" | Select-Object -Last 5

# 2. JWT keys (idempotente)
Write-Host "`nStep 2: JWT keys" -ForegroundColor Yellow
if (-not (Test-Path jwt_private.pem)) {
    & openssl genrsa -out jwt_private.pem 2048 2>&1 | Out-Null
    & openssl rsa -in jwt_private.pem -pubout -out jwt_public.pem 2>&1 | Out-Null
    Write-Host "  JWT keys generate." -ForegroundColor Green
} else {
    Write-Host "  JWT keys gia' presenti." -ForegroundColor Gray
}

# 3. Infra docker
Write-Host "`nStep 3: docker compose up -d postgres qdrant redis" -ForegroundColor Yellow
docker compose up -d postgres qdrant redis 2>&1 | Select-Object -Last 5

Write-Host "  Attesa 10s perche' Postgres sia pronto..."
Start-Sleep -Seconds 10

# 4. Test sequence (tier-by-tier per identificare il failure layer)
$testTiers = @(
    @{ Name = "TIER 1 - Pure unit (no infra)"; Files = "tests/test_config.py tests/test_security_config.py tests/test_chunking.py tests/test_resilience.py" },
    @{ Name = "TIER 2 - DB/Auth (Postgres)";   Files = "tests/test_db_models.py tests/test_auth.py tests/test_rls_enforcement.py" },
    @{ Name = "TIER 3 - Cache (Redis)";        Files = "tests/test_cache.py tests/test_cache_org_isolation.py" },
    @{ Name = "TIER 4 - Vector/Hybrid (Qdrant)"; Files = "tests/test_hybrid_search.py" },
    @{ Name = "TIER 5 - LLM/Agents (LLM API)"; Files = "tests/test_agents.py tests/test_cove.py tests/test_local_router.py" },
    @{ Name = "TIER 6 - External APIs";        Files = "tests/test_eurlex_client.py tests/test_normattiva_client.py" },
    @{ Name = "TIER 7 - API integration";      Files = "tests/test_api_integration.py" },
    @{ Name = "TIER 8 - Monte Carlo (slow)";   Files = "tests/test_monte_carlo.py" }
)

$results = @()
foreach ($tier in $testTiers) {
    Write-Host "`n=== $($tier.Name) ===" -ForegroundColor Cyan
    $log = ".pytest_$($tier.Name -replace '\W','_').log"
    $cmd = "poetry run pytest $($tier.Files) -v --tb=short --no-header"
    Write-Host "  $cmd"
    $output = Invoke-Expression $cmd 2>&1
    $output | Out-File -FilePath $log
    $tail = $output | Select-Object -Last 3
    Write-Host ($tail -join "`n")

    # Estrai pass/fail counts
    $summary = $output | Where-Object { $_ -match '\d+ (passed|failed|error)' } | Select-Object -Last 1
    $results += [PSCustomObject]@{ Tier = $tier.Name; Summary = $summary; Log = $log }
}

# 5. Final summary
Write-Host "`n========== FINAL SUMMARY ==========" -ForegroundColor Green
$results | Format-Table -AutoSize
Write-Host "`nLog files dettagliati: .pytest_*.log nella root."
Write-Host "Per kill criteria G1: TIER 1 deve essere 100% pass. TIER 2-4 >= 90%. TIER 5+ con fallimenti accettabili (LLM API drift)."
