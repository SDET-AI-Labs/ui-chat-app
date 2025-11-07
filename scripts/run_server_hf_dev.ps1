# Dev-only runner to work around TLS interception for HF InferenceClient
param(
  [int]$Port = 8000
)
$env:BACKEND = "hf"
# Disable cert verification only for this spawned process
$env:PYTHONHTTPSVERIFY = "0"
$env:REQUESTS_CA_BUNDLE = ""
$env:CURL_CA_BUNDLE = ""
# Some huggingface flows may honor this flag
$env:HF_HUB_DISABLE_SSL_VERIFY = "1"
 
# Resolve venv python relative to this script; fall back to python on PATH
$venvPython = Join-Path $PSScriptRoot "..\.venv\Scripts\python.exe"
if (-Not (Test-Path $venvPython)) {
  Write-Host "Warning: venv python not found at $venvPython; falling back to 'python' on PATH."
  $venvPython = "python"
}

& $venvPython -m uvicorn chatstack.api.server:app --host 0.0.0.0 --port $Port
