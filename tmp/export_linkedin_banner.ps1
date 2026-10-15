param(
    [Parameter(Mandatory = $true)][string]$Source,
    [Parameter(Mandatory = $true)][string]$Destination
)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing
if (Test-Path -LiteralPath $Destination) { throw 'Destination already exists.' }
$sourceImage = [System.Drawing.Image]::FromFile($Source)
$exportImage = New-Object System.Drawing.Bitmap(1512, 256)
try {
    # The generated composition reserves plain bleed above and below this strip.
    $cropHeight = $sourceImage.Width * 256.0 / 1512.0
    if ($cropHeight -gt $sourceImage.Height) { throw 'Source is too short.' }
    $cropTop = ($sourceImage.Height - $cropHeight) / 2.0
    $graphics = [System.Drawing.Graphics]::FromImage($exportImage)
    try {
        $graphics.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
        $graphics.PixelOffsetMode = [System.Drawing.Drawing2D.PixelOffsetMode]::HighQuality
        $targetRect = New-Object System.Drawing.RectangleF(0, 0, 1512, 256)
        $sourceRect = New-Object System.Drawing.RectangleF(0, $cropTop, $sourceImage.Width, $cropHeight)
        $graphics.DrawImage($sourceImage, $targetRect, $sourceRect, [System.Drawing.GraphicsUnit]::Pixel)
    } finally { $graphics.Dispose() }
    $exportImage.Save($Destination, [System.Drawing.Imaging.ImageFormat]::Png)
} finally {
    $exportImage.Dispose()
    $sourceImage.Dispose()
}
$verifiedImage = [System.Drawing.Image]::FromFile($Destination)
try {
    if ($verifiedImage.Width -ne 1512 -or $verifiedImage.Height -ne 256) { throw 'Incorrect export dimensions.' }
    $file = Get-Item -LiteralPath $Destination
    if ($file.Length -gt 3MB) { throw 'LinkedIn file limit exceeded.' }
    [pscustomobject]@{ Path = $file.FullName; Width = $verifiedImage.Width; Height = $verifiedImage.Height; Bytes = $file.Length }
} finally { $verifiedImage.Dispose() }
