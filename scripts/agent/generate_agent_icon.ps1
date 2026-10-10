param(
    [string]$ProjectRoot = (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))
)

$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Drawing

$AssetDir = Join-Path $ProjectRoot "tools\Om0rxAgent\assets"
$IconPath = Join-Path $AssetDir "om0rx-agent.ico"
$PreviewPath = Join-Path $AssetDir "om0rx-agent-256.png"
New-Item -ItemType Directory -Force -Path $AssetDir | Out-Null

function New-AgentBitmap {
    param([int]$Size)

    $bmp = New-Object System.Drawing.Bitmap $Size, $Size, ([System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
    $g.Clear([System.Drawing.Color]::Transparent)

    $scale = $Size / 256.0
    function S([float]$value) { return [float]($value * $scale) }

    $bgRect = [System.Drawing.RectangleF]::new((S 18), (S 18), (S 220), (S 220))
    $bgBrush = [System.Drawing.Drawing2D.LinearGradientBrush]::new(
        $bgRect,
        [System.Drawing.Color]::FromArgb(255, 8, 37, 64),
        [System.Drawing.Color]::FromArgb(255, 15, 112, 105),
        [System.Drawing.Drawing2D.LinearGradientMode]::ForwardDiagonal)
    $g.FillEllipse($bgBrush, $bgRect)

    $ringPen = [System.Drawing.Pen]::new([System.Drawing.Color]::FromArgb(245, 238, 245, 246), (S 10))
    $g.DrawEllipse($ringPen, (S 28), (S 28), (S 200), (S 200))

    $accentPen = [System.Drawing.Pen]::new([System.Drawing.Color]::FromArgb(255, 34, 211, 238), (S 13))
    $accentPen.StartCap = [System.Drawing.Drawing2D.LineCap]::Round
    $accentPen.EndCap = [System.Drawing.Drawing2D.LineCap]::Round
    $g.DrawArc($accentPen, (S 46), (S 46), (S 164), (S 164), 205, 128)

    $towerPen = [System.Drawing.Pen]::new([System.Drawing.Color]::White, (S 12))
    $towerPen.StartCap = [System.Drawing.Drawing2D.LineCap]::Round
    $towerPen.EndCap = [System.Drawing.Drawing2D.LineCap]::Round
    $g.DrawLine($towerPen, (S 128), (S 72), (S 128), (S 174))
    $g.DrawLine($towerPen, (S 92), (S 172), (S 164), (S 172))
    $g.DrawLine($towerPen, (S 128), (S 105), (S 91), (S 139))
    $g.DrawLine($towerPen, (S 128), (S 105), (S 165), (S 139))

    $wavePen = [System.Drawing.Pen]::new([System.Drawing.Color]::FromArgb(230, 255, 207, 92), (S 9))
    $wavePen.StartCap = [System.Drawing.Drawing2D.LineCap]::Round
    $wavePen.EndCap = [System.Drawing.Drawing2D.LineCap]::Round
    $g.DrawArc($wavePen, (S 61), (S 63), (S 134), (S 91), 205, 130)
    $g.DrawArc($wavePen, (S 42), (S 45), (S 172), (S 126), 207, 126)

    $dotBrush = [System.Drawing.SolidBrush]::new([System.Drawing.Color]::FromArgb(255, 255, 207, 92))
    $g.FillEllipse($dotBrush, (S 116), (S 59), (S 24), (S 24))

    $g.Dispose()
    $bgBrush.Dispose()
    $ringPen.Dispose()
    $accentPen.Dispose()
    $towerPen.Dispose()
    $wavePen.Dispose()
    $dotBrush.Dispose()
    return $bmp
}

$preview = New-AgentBitmap -Size 256
$preview.Save($PreviewPath, [System.Drawing.Imaging.ImageFormat]::Png)
$preview.Dispose()

$iconBitmap = New-AgentBitmap -Size 64
$iconSize = 64
$rowBytes = $iconSize * 4
$maskRowBytes = [int](($iconSize + 31) / 32) * 4
$pixelBytes = New-Object byte[] ($rowBytes * $iconSize)
$rect = [System.Drawing.Rectangle]::new(0, 0, $iconSize, $iconSize)
$bitmapData = $iconBitmap.LockBits(
    $rect,
    [System.Drawing.Imaging.ImageLockMode]::ReadOnly,
    [System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
try {
    for ($row = 0; $row -lt $iconSize; $row++) {
        $source = [IntPtr]::Add($bitmapData.Scan0, $row * $bitmapData.Stride)
        [Runtime.InteropServices.Marshal]::Copy($source, $pixelBytes, $row * $rowBytes, $rowBytes)
    }
}
finally {
    $iconBitmap.UnlockBits($bitmapData)
    $iconBitmap.Dispose()
}
$resourceLength = 40 + $pixelBytes.Length + ($maskRowBytes * $iconSize)

# Write a deterministic classic DIB-backed ICO. Icon.Save() serializes an HICON
# allocated by Windows and changes opaque bytes between otherwise identical
# builds, while the .NET resource compiler does not accept every PNG-backed ICO.
$fs = [System.IO.File]::Open($IconPath, [System.IO.FileMode]::Create, [System.IO.FileAccess]::Write)
$writer = New-Object System.IO.BinaryWriter $fs
try {
    $writer.Write([uint16]0)                 # reserved
    $writer.Write([uint16]1)                 # ICO image type
    $writer.Write([uint16]1)                 # image count
    $writer.Write([byte]64)                  # width
    $writer.Write([byte]64)                  # height
    $writer.Write([byte]0)                   # palette size
    $writer.Write([byte]0)                   # reserved
    $writer.Write([uint16]1)                 # color planes
    $writer.Write([uint16]32)                # bits per pixel
    $writer.Write([uint32]$resourceLength)   # resource length
    $writer.Write([uint32]22)                # resource offset

    $writer.Write([uint32]40)                # BITMAPINFOHEADER size
    $writer.Write([int32]$iconSize)          # width
    $writer.Write([int32]($iconSize * 2))    # XOR + AND mask height
    $writer.Write([uint16]1)                 # planes
    $writer.Write([uint16]32)                # bits per pixel
    $writer.Write([uint32]0)                 # BI_RGB
    $writer.Write([uint32]$pixelBytes.Length)
    $writer.Write([int32]0)                  # horizontal pixels/metre
    $writer.Write([int32]0)                  # vertical pixels/metre
    $writer.Write([uint32]0)                 # palette entries
    $writer.Write([uint32]0)                 # important colours

    # ICO DIB pixels are bottom-up BGRA rows. Alpha carries transparency; the
    # legacy one-bit AND mask remains zero-filled for modern Windows.
    for ($row = $iconSize - 1; $row -ge 0; $row--) {
        $writer.Write($pixelBytes, $row * $rowBytes, $rowBytes)
    }
    $writer.Write((New-Object byte[] ($maskRowBytes * $iconSize)))
}
finally {
    $writer.Dispose()
    $fs.Dispose()
}

Write-Host "Generated $IconPath" -ForegroundColor Green
Write-Host "Generated $PreviewPath" -ForegroundColor Green
