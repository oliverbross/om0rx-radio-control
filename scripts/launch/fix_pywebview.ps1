# Fix pywebview installation for Python 3.14+
# This script handles the pythonnet build issue with Python 3.14

Write-Host "`n🔧 FlexRadio - PyWebView Installation Fixer" -ForegroundColor Cyan
Write-Host "============================================`n" -ForegroundColor Cyan

Write-Host "📋 Checking Python version..." -ForegroundColor Yellow
python --version

Write-Host "`n🧹 Step 1: Cleaning pip cache..." -ForegroundColor Cyan
pip cache purge 2>&1 | Out-Null
Write-Host "✅ Cache cleaned`n" -ForegroundColor Green

Write-Host "📦 Step 2: Upgrading pip, setuptools, and wheel..." -ForegroundColor Cyan
Write-Host "   (this may take a moment...)" -ForegroundColor Gray
pip install --upgrade pip setuptools wheel 2>&1 | Out-Null
Write-Host "✅ pip, setuptools, wheel updated`n" -ForegroundColor Green

Write-Host "📥 Step 3: Installing pywebview with pre-built wheels..." -ForegroundColor Cyan
Write-Host "   (trying to avoid pythonnet compilation...)" -ForegroundColor Gray
pip install pywebview --only-binary :all: --upgrade 2>&1

$checkWebview = python -c "import webview; print('OK')" 2>&1
if ($checkWebview -contains "OK") {
    Write-Host "`n✅ SUCCESS! pywebview is now installed!" -ForegroundColor Green
    Write-Host "`n🚀 You can now run:" -ForegroundColor Cyan
    Write-Host "   .\launch_windows.ps1`n" -ForegroundColor Gray
} else {
    Write-Host "`n⚠️  Pre-built wheels not available, trying standard installation..." -ForegroundColor Yellow
    Write-Host "   (This may compile from source...)" -ForegroundColor Gray
    pip install pywebview==5.2 --upgrade 2>&1
    
    $checkWebview = python -c "import webview; print('OK')" 2>&1
    if ($checkWebview -contains "OK") {
        Write-Host "`n✅ SUCCESS! pywebview is now installed!" -ForegroundColor Green
        Write-Host "`n🚀 You can now run:" -ForegroundColor Cyan
        Write-Host "   .\launch_windows.ps1`n" -ForegroundColor Gray
    } else {
        Write-Host "`n❌ Installation still failed" -ForegroundColor Red
        Write-Host "`n💡 Alternative Solution:" -ForegroundColor Yellow
        Write-Host "   Use the browser launcher instead (no installation needed!):" -ForegroundColor Cyan
        Write-Host "   http://localhost:8080/launcher.html`n" -ForegroundColor Gray
        Write-Host "   This gives you the same functionality, just in a browser window`n" -ForegroundColor Gray
    }
}