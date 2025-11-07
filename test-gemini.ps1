# Test Google Gemini API Connectivity
# Make sure to add your GEMINI_API_KEY to .env file first

# Load environment variables from .env file
Get-Content .env | ForEach-Object {
    if ($_ -match '^\s*([^#][^=]*)\s*=\s*(.*)$') {
        $key = $matches[1].Trim()
        $value = $matches[2].Trim()
        [Environment]::SetEnvironmentVariable($key, $value, 'Process')
    }
}

$GEMINI_API_KEY = $env:GEMINI_API_KEY
$GEMINI_MODEL = if ([string]::IsNullOrWhiteSpace($env:GEMINI_MODEL)) { "gemini-1.5-flash" } else { $env:GEMINI_MODEL }
$GEMINI_API_BASE = if ([string]::IsNullOrWhiteSpace($env:GEMINI_API_BASE)) { "https://generativelanguage.googleapis.com/v1beta" } else { $env:GEMINI_API_BASE }

# Build model candidates (try common aliases if the base one fails)
$modelCandidates = New-Object System.Collections.Generic.List[string]
$modelCandidates.Add($GEMINI_MODEL)
if ($GEMINI_MODEL -eq 'gemini-1.5-flash') {
    $modelCandidates.Add('gemini-1.5-flash-latest')
    $modelCandidates.Add('gemini-1.5-flash-001')
    # Optional test-only fallback if 1.5 is unavailable on this key
    $modelCandidates.Add('gemini-flash-latest')
}

if ([string]::IsNullOrWhiteSpace($GEMINI_API_KEY)) {
    Write-Host "ERROR: GEMINI_API_KEY is not set in .env file" -ForegroundColor Red
    Write-Host ""
    Write-Host "Please follow these steps:" -ForegroundColor Yellow
    Write-Host "1. Go to https://aistudio.google.com/app/apikey" -ForegroundColor Cyan
    Write-Host "2. Sign in with your Google account" -ForegroundColor Cyan
    Write-Host "3. Click 'Create API Key' button" -ForegroundColor Cyan
    Write-Host "4. Copy the generated API key" -ForegroundColor Cyan
    Write-Host "5. Add it to .env file: GEMINI_API_KEY=your-key-here" -ForegroundColor Cyan
    exit 1
}

Write-Host "Testing Gemini API with key: $($GEMINI_API_KEY.Substring(0, [Math]::Min(10, $GEMINI_API_KEY.Length)))..." -ForegroundColor Cyan
Write-Host "Model: $GEMINI_MODEL" -ForegroundColor Cyan
Write-Host "API Base: $GEMINI_API_BASE" -ForegroundColor Cyan
Write-Host ""

# Prepare the request body
$body = @{
    contents = @(
        @{
            parts = @(
                @{
                    text = "Hello! Please respond with a brief greeting to confirm the API is working."
                }
            )
        }
    )
} | ConvertTo-Json -Depth 10

# Make the API request
try {
    Write-Host "Sending request to Gemini API..." -ForegroundColor Yellow
    
    $baseCandidates = New-Object System.Collections.Generic.List[string]
    $baseCandidates.Add($GEMINI_API_BASE.TrimEnd('/'))
    if ($GEMINI_API_BASE -match '/v1beta$') {
        $baseCandidates.Add(($GEMINI_API_BASE -replace '/v1beta$', '/v1').TrimEnd('/'))
    } elseif ($GEMINI_API_BASE -match '/v1$') {
        $baseCandidates.Add(($GEMINI_API_BASE -replace '/v1$', '/v1beta').TrimEnd('/'))
    } else {
        $baseCandidates.Add('https://generativelanguage.googleapis.com/v1')
        $baseCandidates.Add('https://generativelanguage.googleapis.com/v1beta')
    }

    $response = $null
    $lastError = $null
    foreach ($b in $baseCandidates) {
        foreach ($m in $modelCandidates) {
            $url = "$b/models/$($m):generateContent?key=$($GEMINI_API_KEY)"
            $logUrl = $url -replace [Regex]::Escape($GEMINI_API_KEY), '***'
            Write-Host "Trying: $logUrl" -ForegroundColor DarkGray
            try {
                $response = Invoke-RestMethod -Uri $url -Method Post -ContentType "application/json" -Body $body -ErrorAction Stop
                break
            } catch {
                $lastError = $_
                continue
            }
        }
        if ($response) { break }
    }
    if (-not $response) { throw $lastError }
    
    Write-Host "SUCCESS! Gemini API is working!" -ForegroundColor Green
    Write-Host ""
    Write-Host "Response from Gemini:" -ForegroundColor Cyan
    Write-Host "----------------------------------------" -ForegroundColor Gray
    
    if ($response.candidates -and $response.candidates.Count -gt 0) {
        $text = $response.candidates[0].content.parts[0].text
        Write-Host $text -ForegroundColor White
    } else {
        Write-Host $($response | ConvertTo-Json -Depth 10) -ForegroundColor White
    }
    
    Write-Host "----------------------------------------" -ForegroundColor Gray
    Write-Host ""
    Write-Host "Gemini API integration is ready to use!" -ForegroundColor Green
    
} catch {
    Write-Host "ERROR: Failed to connect to Gemini API" -ForegroundColor Red
    Write-Host ""
    Write-Host "Error Details:" -ForegroundColor Yellow
    Write-Host $_.Exception.Message -ForegroundColor Red
    
    if ($_.Exception.Response) {
        $reader = New-Object System.IO.StreamReader($_.Exception.Response.GetResponseStream())
        $responseBody = $reader.ReadToEnd()
        Write-Host ""
        Write-Host "API Response:" -ForegroundColor Yellow
        Write-Host $responseBody -ForegroundColor Red
    }
    
    Write-Host ""
    Write-Host "Common issues:" -ForegroundColor Yellow
    Write-Host "- Invalid API key (check your .env file)" -ForegroundColor Cyan
    Write-Host "- API key not activated yet (can take a few minutes)" -ForegroundColor Cyan
    Write-Host "- Billing not enabled (required for production use)" -ForegroundColor Cyan
    exit 1
}
