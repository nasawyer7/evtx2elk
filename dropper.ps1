# --- CONFIGURATION ---
$DropFolder = "C:\Logs_Drop_Folder"
$ProcessedFolder = "C:\Logs_Drop_Folder\Processed"
$WinlogbeatDir = "C:\Program Files\Winlogbeat"
$ConfigFile = "evtx-ingest.yml"
# ---------------------
if (!(Test-Path $ProcessedFolder)) { New-Item -ItemType Directory -Path $ProcessedFolder }

#  Get all .evtx files
$Files = Get-ChildItem -Path $DropFolder -Filter *.evtx

if ($Files.Count -eq 0) {
    Write-Host "No .evtx files found in $DropFolder." -ForegroundColor Yellow
}

foreach ($File in $Files) {
    Write-Host "Processing: $($File.Name)..." -ForegroundColor Cyan

    # mem whipe
    Remove-Item "$WinlogbeatDir\data\registry" -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item "$WinlogbeatDir\data\.winlogbeat.yml" -Force -ErrorAction SilentlyContinue
    Remove-Item "$WinlogbeatDir\data\evtx-registry.yml" -Force -ErrorAction SilentlyContinue

    # upload step
    $Process = Start-Process -FilePath "$WinlogbeatDir\winlogbeat.exe" `
               -ArgumentList "-e", "-c", "$ConfigFile", "-E", "EVTX_FILE=`"$($File.FullName)`"" `
               -WorkingDirectory $WinlogbeatDir `
               -Wait -NoNewWindow -PassThru

    # renaming and moving logs
    if ($Process.ExitCode -eq 0) {
        $Timestamp = Get-Date -Format "yyyy-MM-dd_HH-mm-ss"
        $NewName = "$($File.BaseName)_$Timestamp$($File.Extension)"
        $DestinationPath = Join-Path -Path $ProcessedFolder -ChildPath $NewName

        Move-Item -Path $File.FullName -Destination $DestinationPath -Force
        
        Write-Host "Worked! Moved to: $NewName" -ForegroundColor Green
    }
    else {
        Write-Host "Error uploading $($File.Name). Check logs." -ForegroundColor Red
    }
}
