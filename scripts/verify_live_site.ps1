# Post-deploy smoke check for the live NormaAI site.
# Run after every Vercel deploy:  pwsh scripts/verify_live_site.ps1
# Optional:  pwsh scripts/verify_live_site.ps1 -BaseUrl https://normaai.org
#
# Checks are read-only except the lead-form probe, which submits with the
# honeypot field filled so the serverless route silently drops it (no fake
# lead reaches the founder inbox).

param(
    [string]$BaseUrl = 'https://normaai-psi.vercel.app'
)

$ErrorActionPreference = 'Continue'
$failures = 0

function Check {
    param([string]$Name, [scriptblock]$Probe)
    try {
        $result = & $Probe
        if ($result) {
            Write-Host "[PASS] $Name" -ForegroundColor Green
        } else {
            Write-Host "[FAIL] $Name" -ForegroundColor Red
            $script:failures++
        }
    } catch {
        Write-Host "[FAIL] $Name - $($_.Exception.Message)" -ForegroundColor Red
        $script:failures++
    }
}

Write-Host "Verifying $BaseUrl`n"

Check 'Home responds 200' {
    (Invoke-WebRequest -Uri "$BaseUrl/" -UseBasicParsing).StatusCode -eq 200
}

Check 'Home shows Codex 2025-2029 (not stale 2025-2028)' {
    $html = (Invoke-WebRequest -Uri "$BaseUrl/" -UseBasicParsing).Content
    ($html -match '2025[--]2029') -and ($html -notmatch '2025[--]2028')
}

Check 'No 2024/XXX placeholder citation' {
    $html = (Invoke-WebRequest -Uri "$BaseUrl/" -UseBasicParsing).Content
    $html -notmatch '2024/XXX'
}

Check 'CSDDD date is post-Omnibus (26 luglio 2028, no luglio 2027)' {
    $html = (Invoke-WebRequest -Uri "$BaseUrl/" -UseBasicParsing).Content
    ($html -match '26 luglio 2028') -and ($html -notmatch 'luglio 2027')
}

Check 'robots.txt serves 200' {
    (Invoke-WebRequest -Uri "$BaseUrl/robots.txt" -UseBasicParsing).StatusCode -eq 200
}

Check 'sitemap.xml serves 200' {
    (Invoke-WebRequest -Uri "$BaseUrl/sitemap.xml" -UseBasicParsing).StatusCode -eq 200
}

Check 'og-image.png serves 200' {
    (Invoke-WebRequest -Uri "$BaseUrl/og-image.png" -Method Head -UseBasicParsing).StatusCode -eq 200
}

Check 'Codex PDF serves 200' {
    (Invoke-WebRequest -Uri "$BaseUrl/codex-post-omnibus-2025-2029.pdf" -Method Head -UseBasicParsing).StatusCode -eq 200
}

Check '/codex redirect preserves ?lead= tracking param' {
    try {
        Invoke-WebRequest -Uri "$BaseUrl/codex?lead=smoketest" -Method Head -MaximumRedirection 0 -UseBasicParsing | Out-Null
        $false  # no redirect happened
    } catch {
        $loc = $_.Exception.Response.Headers.Location
        "$loc" -match 'lead=smoketest'
    }
}

Check 'Lead route alive (honeypot probe - dropped silently, no email)' {
    $body = @{ email = 'probe@example.com'; website = 'bot-canary'; source = 'smoke_test' } | ConvertTo-Json
    $r = Invoke-WebRequest -Uri "$BaseUrl/api/leads" -Method Post -Body $body -ContentType 'application/json' -UseBasicParsing
    $r.StatusCode -eq 200
}

Check 'Lead route rejects invalid email with 422' {
    try {
        $body = @{ email = 'not-an-email' } | ConvertTo-Json
        Invoke-WebRequest -Uri "$BaseUrl/api/leads" -Method Post -Body $body -ContentType 'application/json' -UseBasicParsing | Out-Null
        $false
    } catch {
        $_.Exception.Response.StatusCode.value__ -eq 422
    }
}

Write-Host ""
if ($failures -eq 0) {
    Write-Host "ALL CHECKS PASSED - il sito live è coerente col repo." -ForegroundColor Green
    exit 0
} else {
    Write-Host "$failures CHECK FALLITI - vedi sopra." -ForegroundColor Red
    exit 1
}
