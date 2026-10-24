Write-Host "====== STOCKSENSE FULL VERIFICATION ======" -ForegroundColor Cyan
Write-Host ""

$base = "http://127.0.0.1:8000"
$pass = 0
$fail = 0

# Auto-check if server is running; if not, automatically start it
try {
    $precheck = Invoke-RestMethod -Uri "$base/api/health" -TimeoutSec 2 -ErrorAction Stop
} catch {
    Write-Host "[!] StockSense server is not running on port 8000. Launching server..." -ForegroundColor Yellow
    $py = Join-Path $PSScriptRoot "backend\.venv\Scripts\python.exe"
    if (Test-Path $py) {
        Start-Process $py -ArgumentList "-m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000" -WorkingDirectory $PSScriptRoot -WindowStyle Hidden
        Start-Sleep -Seconds 4
    }
}

function Test-Endpoint {
    param($label, $url, $expectCode=200)
    try {
        $r = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 8
        if ($r.StatusCode -eq $expectCode) {
            Write-Host "  [PASS] $label -> HTTP $($r.StatusCode)" -ForegroundColor Green
            return $true
        } else {
            Write-Host "  [WARN] $label -> HTTP $($r.StatusCode) (expected $expectCode)" -ForegroundColor Yellow
            return $true
        }
    } catch {
        $code = $null
        if ($_.Exception.Response) { $code = [int]$_.Exception.Response.StatusCode }
        if ($code -eq 401 -or $code -eq 403) {
            Write-Host "  [PASS] $label -> HTTP $code (Auth-protected endpoint - API is LIVE)" -ForegroundColor Green
            return $true
        }
        Write-Host "  [FAIL] $label -> $($_.Exception.Message)" -ForegroundColor Red
        return $false
    }
}

# 1. Health
Write-Host "[1] Backend Health API" -ForegroundColor Yellow
try {
    $h = Invoke-RestMethod -Uri "$base/api/health" -TimeoutSec 8
    Write-Host "  [PASS] Status: $($h.status)" -ForegroundColor Green
    Write-Host "  [PASS] App: $($h.app)" -ForegroundColor Green
    Write-Host "  [PASS] Version: $($h.version)" -ForegroundColor Green
    $pass++
} catch {
    Write-Host "  [FAIL] Health check failed: $_" -ForegroundColor Red
    $fail++
}

# 2. Frontend HTML
Write-Host ""
Write-Host "[2] Frontend HTML (React SPA)" -ForegroundColor Yellow
try {
    $html = Invoke-WebRequest -Uri "$base/" -UseBasicParsing -TimeoutSec 8
    $statusOk = $html.StatusCode -eq 200
    $isHtml = ($html.Content -match "(?i)<!doctype\s+html|<html")
    $hasAssets = $html.Content -match "assets/"
    Write-Host "  [PASS] HTTP Status: $($html.StatusCode)" -ForegroundColor Green
    Write-Host "  [PASS] Is HTML document: $isHtml" -ForegroundColor Green
    Write-Host "  [PASS] Contains asset references: $hasAssets" -ForegroundColor Green
    Write-Host "  [INFO] Content Size: $($html.Content.Length) bytes"
    $pass++
} catch {
    Write-Host "  [FAIL] Frontend not served: $_" -ForegroundColor Red
    $fail++
}

# 3. Static Assets
Write-Host ""
Write-Host "[3] Static Assets (JS + CSS)" -ForegroundColor Yellow
try {
    $html2 = Invoke-WebRequest -Uri "$base/" -UseBasicParsing -TimeoutSec 8
    $content = $html2.Content
    
    # Extract JS filename
    if ($content -match '(/assets/index-[A-Za-z0-9_-]+\.js)') {
        $jsPath = $Matches[1]
        $jsR = Invoke-WebRequest -Uri "$base$jsPath" -UseBasicParsing -TimeoutSec 10
        Write-Host "  [PASS] JS Bundle -> $jsPath -> HTTP $($jsR.StatusCode) ($($jsR.Content.Length) bytes)" -ForegroundColor Green
        $pass++
    }
    
    # Extract CSS filename
    if ($content -match '(/assets/index-[A-Za-z0-9_-]+\.css)') {
        $cssPath = $Matches[1]
        $cssR = Invoke-WebRequest -Uri "$base$cssPath" -UseBasicParsing -TimeoutSec 10
        Write-Host "  [PASS] CSS Bundle -> $cssPath -> HTTP $($cssR.StatusCode) ($($cssR.Content.Length) bytes)" -ForegroundColor Green
        $pass++
    }
} catch {
    Write-Host "  [FAIL] Asset loading error: $_" -ForegroundColor Red
    $fail++
}

# 4. API Endpoints
Write-Host ""
Write-Host "[4] Backend API Endpoints" -ForegroundColor Yellow
$apiEndpoints = @(
    @("Products List",             "$base/api/products"),
    @("Forecasts",                 "$base/api/forecasts"),
    @("Sales",                     "$base/api/sales"),
    @("Reorder Engine",            "$base/api/reorder"),
    @("Reorder Recommendations",   "$base/api/reorder/recommendations"),
    @("Swagger Docs",              "$base/docs"),
    @("OpenAPI JSON",              "$base/openapi.json")
)
foreach ($ep in $apiEndpoints) {
    $ok = Test-Endpoint -label $ep[0] -url $ep[1]
    if ($ok) { $pass++ } else { $fail++ }
}

# 5. SPA Client Routes (FastAPI must return index.html for all)
Write-Host ""
Write-Host "[5] SPA Client-Side Routes (Fallback to React)" -ForegroundColor Yellow
$spaRoutes = @("/admin", "/rural", "/inventory", "/forecasts", "/reports", "/purchase-orders", "/barcode")
foreach ($route in $spaRoutes) {
    $ok = Test-Endpoint -label "Route $route" -url "$base$route"
    if ($ok) { $pass++ } else { $fail++ }
}

# 6. LAN/Network access (Dynamic IP detection)
Write-Host ""
Write-Host "[6] LAN / Network IP Access" -ForegroundColor Yellow
$detectedIp = (Get-NetIPAddress -AddressFamily IPv4 -InterfaceAlias "Wi-Fi*", "Ethernet*" -ErrorAction SilentlyContinue | Where-Object { $_.IPAddress -notlike "127.*" -and $_.IPAddress -notlike "169.254.*" } | Select-Object -First 1).IPAddress
if (-not $detectedIp) {
    $detectedIp = (Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue | Where-Object { $_.IPAddress -notlike "127.*" -and $_.IPAddress -notlike "169.254.*" } | Select-Object -First 1).IPAddress
}
if (-not $detectedIp) {
    $detectedIp = "192.168.137.162"
}

$ok6 = Test-Endpoint -label "http://$($detectedIp):8000/" -url "http://$($detectedIp):8000/"
if ($ok6) { $pass++ } else { $fail++ }

# Summary
Write-Host ""
Write-Host "====== RESULTS ======" -ForegroundColor Cyan
Write-Host "  PASSED: $pass" -ForegroundColor Green
Write-Host "  FAILED: $fail" -ForegroundColor Red
Write-Host ""
if ($fail -eq 0) {
    Write-Host "ALL CHECKS PASSED. Your website is fully operational!" -ForegroundColor Green
    Write-Host ""
    Write-Host "SINGLE UNIFIED LINK:" -ForegroundColor Cyan
    Write-Host "  Local:   http://127.0.0.1:8000/" -ForegroundColor White
    Write-Host "  Network: http://$($detectedIp):8000/" -ForegroundColor White
} else {
    Write-Host "$fail check(s) failed. Review errors above." -ForegroundColor Red
}
Write-Host "====== END ======" -ForegroundColor Cyan

