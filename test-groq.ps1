# Test Groq via OpenAI-like backend through local FastAPI server
# Prereqs: .env has BACKEND=openai_like, OPENAI_API_BASE=https://api.groq.com/openai/v1,
# OPENAI_MODEL=llama-3.1-8b-instant, and OPENAI_API_KEY is set (do NOT commit secrets).

# Load .env into process env
Get-Content .env | ForEach-Object {
    if ($_ -match '^\s*([^#][^=]*)\s*=\s*(.*)$') {
        $key = $matches[1].Trim()
        $value = $matches[2].Trim()
        [Environment]::SetEnvironmentVariable($key, $value, 'Process')
    }
}

$OPENAI_API_KEY = $env:OPENAI_API_KEY
if ([string]::IsNullOrWhiteSpace($OPENAI_API_KEY)) {
    Write-Host "ERROR: OPENAI_API_KEY is not set. Add your Groq key to .env or set it in this session." -ForegroundColor Red
    Write-Host "Example (PowerShell, session only):" -ForegroundColor Yellow
    Write-Host "$env:OPENAI_API_KEY = 'sk_groq_...'
"
    exit 1
}

# Ensure server is running; if health fails, start it
function Test-Health {
    try {
        return Invoke-RestMethod -Uri "http://localhost:8000/health" -TimeoutSec 5
    } catch {
        return $null
    }
}

$health = Test-Health
if (-not $health) {
    Write-Host "Starting server..." -ForegroundColor Yellow
    Start-Process -WindowStyle Hidden -FilePath ".\.venv\Scripts\python.exe" -ArgumentList "-m","uvicorn","src.chatstack.api.server:app","--host","0.0.0.0","--port","8000","--reload"
    Start-Sleep -Seconds 2
    $health = Test-Health
}

if (-not $health) {
    Write-Host "ERROR: Server is not responding on http://localhost:8000" -ForegroundColor Red
    exit 1
}

Write-Host "Health:" -ForegroundColor Cyan
$health | Format-Table -AutoSize

# Non-stream test
Write-Host "\nTesting /chat (non-stream)..." -ForegroundColor Yellow
$body = '{"messages":[{"role":"user","content":"Give me 3 examples of boundary test cases"}] }'
try {
    $resp = Invoke-RestMethod -Uri "http://localhost:8000/chat" -Method POST -Body $body -ContentType "application/json" -TimeoutSec 60
    Write-Host "Assistant:" -ForegroundColor Cyan
    if ($resp.content) { Write-Host $resp.content } else { $resp | ConvertTo-Json -Depth 10 | Write-Host }
} catch {
    Write-Host "Non-stream request failed:" -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    if ($_.Exception.Response) {
        $reader = New-Object System.IO.StreamReader($_.Exception.Response.GetResponseStream())
        $responseBody = $reader.ReadToEnd()
        Write-Host $responseBody -ForegroundColor Red
    }
}

# Stream test
Write-Host "\nTesting /chat/stream (SSE)..." -ForegroundColor Yellow
$sbody = '{"messages":[{"role":"user","content":"Short explain: equivalence partitioning"}] }'
try {
    $raw = Invoke-WebRequest -UseBasicParsing -Uri "http://localhost:8000/chat/stream" -Method POST -Body $sbody -ContentType "application/json" -TimeoutSec 120
    $lines = ($raw.Content -split "\r?\n")
    $sse = $lines | Where-Object { $_ -match '^data:' }
    Write-Host "First 6 SSE data lines:" -ForegroundColor Cyan
    $sse | Select-Object -First 6 | ForEach-Object { Write-Host $_ }
} catch {
    Write-Host "Streaming request failed:" -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    if ($_.Exception.Response) {
        $reader = New-Object System.IO.StreamReader($_.Exception.Response.GetResponseStream())
        $responseBody = $reader.ReadToEnd()
        Write-Host $responseBody -ForegroundColor Red
    }
}

Write-Host "\nDone." -ForegroundColor Green