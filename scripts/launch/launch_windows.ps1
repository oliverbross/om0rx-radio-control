# FlexRadio Multi-Window Launcher (pywebview)
# Launches three synchronized windows as native desktop applications

Write-Host "`n⚡ FlexRadio Multi-Window Launcher" -ForegroundColor Cyan
Write-Host "==================================`n" -ForegroundColor Cyan

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent (Split-Path -Parent $ScriptDir)

# Check if pywebview is installed
Write-Host "📦 Checking dependencies..." -ForegroundColor Yellow
$pywebviewCheck = python -c "import webview" 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ pywebview is not installed!" -ForegroundColor Red
    Write-Host "`n📥 Installing pywebview (this may take a minute)..." -ForegroundColor Yellow
    
    # Try standard installation first
    Write-Host "   Attempting standard installation..." -ForegroundColor Gray
    pip install pywebview --upgrade 2>&1 | Out-Null
    
    $pywebviewCheck = python -c "import webview" 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "✅ pywebview installed successfully!" -ForegroundColor Green
    } else {
        Write-Host "⚠️  Standard installation failed, trying alternative method..." -ForegroundColor Yellow
        
        # Try with specific version that works better with Python 3.14
        Write-Host "   Installing compatible version (pywebview 5.x)..." -ForegroundColor Gray
        pip install "pywebview==5.2" --no-deps 2>&1 | Out-Null
        
        $pywebviewCheck = python -c "import webview" 2>&1
        if ($LASTEXITCODE -eq 0) {
            Write-Host "✅ pywebview installed (compatible version)!" -ForegroundColor Green
        } else {
            Write-Host "`n❌ Installation failed. Trying one more method..." -ForegroundColor Red
            
            # Last resort: try with pre-built wheels
            Write-Host "   Using pre-built wheels (offline mode)..." -ForegroundColor Gray
            pip install pywebview --only-binary :all: 2>&1 | Out-Null
            
            $pywebviewCheck = python -c "import webview" 2>&1
            if ($LASTEXITCODE -eq 0) {
                Write-Host "✅ pywebview installed using pre-built wheels!" -ForegroundColor Green
            } else {
                Write-Host "`n❌ Could not install pywebview automatically" -ForegroundColor Red
                Write-Host "`n💡 SOLUTION: Please try one of these manual commands:" -ForegroundColor Yellow
                Write-Host "   1. pip install --upgrade pip setuptools wheel" -ForegroundColor Gray
                Write-Host "   2. pip install pywebview --upgrade" -ForegroundColor Gray
                Write-Host "`n   Or use the browser launcher instead:" -ForegroundColor Cyan
                Write-Host "   http://localhost:8080/launcher.html" -ForegroundColor Gray
                exit 1
            }
        }
    }
} else {
    Write-Host "✅ pywebview is installed" -ForegroundColor Green
}

Write-Host "`n📝 Note: Make sure your backend is running!" -ForegroundColor Yellow
Write-Host "   Run: .\start_all.ps1 (from the project root)" -ForegroundColor Gray

Write-Host "`n🚀 Launching FlexRadio windows..." -ForegroundColor Cyan
Write-Host "   (This will open 3 native desktop windows)" -ForegroundColor Gray
Write-Host "`n"

# Launch the Python script
python (Join-Path $ProjectRoot "scripts\launch\launch_windows.py")

Write-Host "`n👋 FlexRadio windows closed" -ForegroundColor Cyan
