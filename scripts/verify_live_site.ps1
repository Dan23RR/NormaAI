# Post-deploy smoke check for the live NormaAI site and its backend.
# Run after every Vercel or backend deploy:  pwsh scripts/verify_live_site.ps1
# Optional:  pwsh scripts/verify_live_site.ps1 -BaseUrl https://normaai.org
#            -ApiVersion <short SHA>  also requires that build on the backend
#            -ApiUrl ''               checks the site only
#
# Checks are read-only except the lead-form probe, which submits with the
# honeypot field filled so the serverless route silently drops it (no fake
# lead reaches the founder inbox).

param(
    [string]$BaseUrl = 'https://normaai-psi.vercel.app',
    [string]$ApiUrl = 'https://api.normaai.org',
    [string]$ApiVersion = ''
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

# The pre-Omnibus date was 26 luglio 2027. "luglio 2027" alone is legitimate:
# the monitoring calendar expects the Commission's CSDDD guidelines then.
Check 'CSDDD date is post-Omnibus (26 luglio 2028, no 26 luglio 2027)' {
    $html = (Invoke-WebRequest -Uri "$BaseUrl/" -UseBasicParsing).Content
    ($html -match '26 luglio 2028') -and ($html -notmatch '26 luglio 2027')
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

if ($ApiUrl) {
    Write-Host "`nVerifying $ApiUrl`n"

    Check 'API /health responds ok' {
        $h = Invoke-RestMethod -Uri "$ApiUrl/health"
        Write-Host "       version $($h.version), qdrant $($h.qdrant), llm $($h.llm)"
        $h.status -eq 'ok'
    }

    if ($ApiVersion) {
        Check "API runs build $ApiVersion" {
            (Invoke-RestMethod -Uri "$ApiUrl/health").version -eq $ApiVersion
        }
    }

    Check 'API /readyz is ready (qdrant, llm and corpus up)' {
        try {
            (Invoke-RestMethod -Uri "$ApiUrl/readyz").status -eq 'ready'
        } catch {
            # A 503 body lists the checks that are down.
            Write-Host "       $($_.ErrorDetails.Message)"
            $false
        }
    }

    Check 'API serves the corpus (GET /api/v1/stats)' {
        $s = Invoke-RestMethod -Uri "$ApiUrl/api/v1/stats"
        Write-Host "       corpus as of $($s.corpus_as_of), $($s.qdrant.points_count) points, $($s.corpus.embedding_model)"
        [bool]$s.corpus_as_of -and ($s.qdrant.points_count -gt 1)
    }

    Check "API CORS allows the site origin" {
        $origin = ([Uri]$BaseUrl).GetLeftPart('Authority')
        $headers = @{
            Origin = $origin
            'Access-Control-Request-Method' = 'POST'
            'Access-Control-Request-Headers' = 'content-type'
        }
        $r = Invoke-WebRequest -Uri "$ApiUrl/api/v1/auth/login" -Method Options -Headers $headers -UseBasicParsing
        "$($r.Headers['Access-Control-Allow-Origin'])" -eq $origin
    }

    # NEXT_PUBLIC_API_BASE_URL is read when Vercel builds: the CSP of the site
    # names the API only after a redeploy with the variable set.
    Check 'Site CSP lets the browser reach the API (NEXT_PUBLIC_API_BASE_URL)' {
        $csp = "$((Invoke-WebRequest -Uri "$BaseUrl/login" -UseBasicParsing).Headers['Content-Security-Policy'])"
        $csp -match ('connect-src[^;]*' + [regex]::Escape($ApiUrl))
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
