# List available Gemini models for your API key

# Load env vars from .env
Get-Content .env | ForEach-Object {
    if ($_ -match '^\s*([^#][^=]*)\s*=\s*(.*)$') {
        $key = $matches[1].Trim()
        $value = $matches[2].Trim()
        [Environment]::SetEnvironmentVariable($key, $value, 'Process')
    }
}

$GEMINI_API_KEY = $env:GEMINI_API_KEY
$GEMINI_API_BASE = if ([string]::IsNullOrWhiteSpace($env:GEMINI_API_BASE)) { "https://generativelanguage.googleapis.com/v1beta" } else { $env:GEMINI_API_BASE }

if ([string]::IsNullOrWhiteSpace($GEMINI_API_KEY)) {
    Write-Host "ERROR: GEMINI_API_KEY is not set" -ForegroundColor Red
    exit 1
}

$base = $GEMINI_API_BASE.TrimEnd('/')
$url = "$base/models?key=$($GEMINI_API_KEY)"
$logUrl = $url -replace [Regex]::Escape($GEMINI_API_KEY), '***'
Write-Host "Fetching models from: $logUrl" -ForegroundColor DarkGray

try {
    $resp = Invoke-RestMethod -Uri $url -Method Get -ErrorAction Stop
    if ($resp.models) {
        Write-Host "Models available (name -> supported methods)" -ForegroundColor Cyan
        foreach ($m in $resp.models) {
            $supports = @()
            if ($m.supportedMethods) { $supports = $m.supportedMethods.Keys }
            elseif ($m.outputTokenLimit) { $supports = @('generateContent?') } # best-effort fallback
            Write-Host ("- {0} -> {1}" -f $m.name, ([string]::Join(', ', $supports)))
        }
    } else {
        Write-Host ($resp | ConvertTo-Json -Depth 10)
    }
} catch {
    Write-Host "ERROR fetching models" -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    if ($_.Exception.Response) {
        $reader = New-Object System.IO.StreamReader($_.Exception.Response.GetResponseStream())
        $responseBody = $reader.ReadToEnd()
        Write-Host $responseBody
    }
    exit 1
}
