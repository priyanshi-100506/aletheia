Write-Host "=== 1. Checking Git Status ===" -ForegroundColor Cyan
git status

Write-Host "`n=== 2. Checking Recent Commits ===" -ForegroundColor Cyan
git log --oneline --decorate -5

Write-Host "`n=== 3. Running Demo Bugs Tests ===" -ForegroundColor Cyan
if (Test-Path "aletheia-demo-bugs") {
    Push-Location "aletheia-demo-bugs"
    try {
        python -m compileall incident_demo
        pytest -q
    } finally {
        Pop-Location
    }
} else {
    Write-Warning "aletheia-demo-bugs directory not found at root."
}
