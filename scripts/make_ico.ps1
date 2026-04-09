param(
  [Parameter(Mandatory = $true)]
  [string]$SourceIcon
)

if (-not (Test-Path $SourceIcon)) {
  Write-Error "Source icon not found: $SourceIcon"
  exit 1
}

if (-not (Get-Command magick -ErrorAction SilentlyContinue)) {
  Write-Error "ImageMagick 'magick' is not installed. Install ImageMagick first."
  exit 1
}

magick $SourceIcon -define icon:auto-resize=16,32,64,128,256,512,1024 icon.ico
Write-Output "Created icon.ico"
