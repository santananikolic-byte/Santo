# PC-Doktor - bringt einen alten Windows-Gamer-PC wieder in Form.
# Start ueber PC-Doktor.bat (holt sich Adminrechte). Laeuft auf Windows 10/11
# mit der eingebauten Windows PowerShell 5.1.

$ErrorActionPreference = 'Continue'
$ProgressPreference = 'SilentlyContinue'   # macht Invoke-WebRequest viel schneller

# --- Grundlagen -------------------------------------------------------------

$Desktop = [Environment]::GetFolderPath('Desktop')
$Bericht = Join-Path $Desktop ("PC-Doktor-Bericht_{0}.txt" -f (Get-Date -Format 'yyyy-MM-dd_HH-mm'))
$Arbeit  = Join-Path $env:TEMP 'PC-Doktor'
New-Item -ItemType Directory -Path $Arbeit -Force | Out-Null

function Titel($text) {
    Write-Host ''
    Write-Host ('=' * 64) -ForegroundColor DarkCyan
    Write-Host "  $text" -ForegroundColor Cyan
    Write-Host ('=' * 64) -ForegroundColor DarkCyan
}
function Ok($text)      { Write-Host "  [OK]    $text" -ForegroundColor Green }
function Warnung($text) { Write-Host "  [!]     $text" -ForegroundColor Yellow }
function Fehler($text)  { Write-Host "  [FEHLER] $text" -ForegroundColor Red }
function Info($text)    { Write-Host "  ...     $text" -ForegroundColor Gray }

function Frage($text) {
    $a = Read-Host "  $text (j/n)"
    return ($a -match '^(j|ja|y|yes)$')
}

function Ist-Admin {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    return (New-Object Security.Principal.WindowsPrincipal $id).IsInRole(
        [Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Hat-Winget {
    return [bool](Get-Command winget -ErrorAction SilentlyContinue)
}

# Alte Windows-Versionen sprechen standardmaessig kein TLS 1.2 -> Downloads brechen ab.
try {
    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor 3072
} catch {}

# Datei robust herunterladen: erst BITS (setzt abgebrochene Downloads fort),
# dann Invoke-WebRequest als Ersatz. Bis zu 3 Versuche.
function Lade-Herunter($url, $ziel) {
    for ($versuch = 1; $versuch -le 3; $versuch++) {
        try {
            if (Test-Path $ziel) { Remove-Item $ziel -Force -ErrorAction SilentlyContinue }
            Info "Download (Versuch $versuch): $url"
            try {
                Start-BitsTransfer -Source $url -Destination $ziel -ErrorAction Stop
            } catch {
                Invoke-WebRequest -Uri $url -OutFile $ziel -UseBasicParsing -ErrorAction Stop
            }
            if ((Test-Path $ziel) -and ((Get-Item $ziel).Length -gt 100KB)) {
                Ok ("Heruntergeladen: {0:N1} MB" -f ((Get-Item $ziel).Length / 1MB))
                return $true
            }
            Warnung 'Datei ist unvollstaendig.'
        } catch {
            Warnung "Download fehlgeschlagen: $($_.Exception.Message)"
        }
        Start-Sleep -Seconds (2 * $versuch)
    }
    Fehler "Download hat nach 3 Versuchen nicht geklappt: $url"
    return $false
}

# --- 1. Diagnose ------------------------------------------------------------

function Diagnose {
    Titel '1) Diagnose - was ist los mit dem PC?'

    $os = Get-CimInstance Win32_OperatingSystem
    $cs = Get-CimInstance Win32_ComputerSystem
    $cpu = Get-CimInstance Win32_Processor | Select-Object -First 1
    Info "Windows:   $($os.Caption) (Build $($os.BuildNumber))"
    Info "Prozessor: $($cpu.Name.Trim())"
    $ramGB = [math]::Round($cs.TotalPhysicalMemory / 1GB, 1)
    $freiGB = [math]::Round($os.FreePhysicalMemory / 1MB, 1)
    Info "RAM:       $ramGB GB gesamt, $freiGB GB frei"
    if ($ramGB -lt 8) { Warnung 'Weniger als 8 GB RAM - fuer aktuelle Spiele knapp.' }

    if ([int]$os.BuildNumber -lt 19041) {
        Warnung 'Windows ist sehr alt. Epic Games & viele Spiele brauchen Windows 10 (2004) oder neuer.'
        Warnung 'Loesung: Windows Update ausfuehren (Einstellungen > Update und Sicherheit).'
    }

    # Laufzeit seit Neustart
    $uptime = (Get-Date) - $os.LastBootUpTime
    if ($uptime.TotalDays -gt 3) {
        Warnung ("PC laeuft seit {0} Tagen ohne Neustart - einmal neu starten hilft oft." -f [int]$uptime.TotalDays)
    }

    # Speicherplatz
    Get-CimInstance Win32_LogicalDisk -Filter 'DriveType=3' | ForEach-Object {
        $frei = [math]::Round($_.FreeSpace / 1GB, 1)
        $ges  = [math]::Round($_.Size / 1GB, 1)
        if ($frei -lt 20) {
            Warnung "Laufwerk $($_.DeviceID) hat nur $frei GB frei von $ges GB - Downloads brechen deshalb ab!"
        } else {
            Ok "Laufwerk $($_.DeviceID): $frei GB frei von $ges GB"
        }
    }

    # Festplatten-Gesundheit
    try {
        Get-PhysicalDisk -ErrorAction Stop | ForEach-Object {
            $typ = if ($_.MediaType -eq 'HDD') { 'HDD (langsam)' } else { "$($_.MediaType)" }
            if ($_.HealthStatus -ne 'Healthy') {
                Fehler "Festplatte '$($_.FriendlyName)' meldet: $($_.HealthStatus) - Daten sichern und Platte tauschen!"
            } else {
                Ok "Festplatte '$($_.FriendlyName)' [$typ] ist gesund"
            }
        }
    } catch { Info 'Festplattenzustand konnte nicht gelesen werden.' }

    # Uhrzeit - falsche Uhr = HTTPS-Fehler = Downloads/Logins scheitern
    try {
        $r = Invoke-WebRequest -Uri 'https://www.microsoft.com' -Method Head -UseBasicParsing -TimeoutSec 10
        Ok 'Internet funktioniert'
        try {
            $netzZeit = [DateTimeOffset]::Parse($r.Headers['Date'], [Globalization.CultureInfo]::InvariantCulture).UtcDateTime
            $abw = [math]::Abs(((Get-Date).ToUniversalTime() - $netzZeit).TotalMinutes)
            if ($abw -gt 5) {
                Fehler ("Die PC-Uhr geht {0} Minuten falsch - das macht Downloads und Logins kaputt! (Punkt 4 behebt das)" -f [int]$abw)
            } else { Ok 'Uhrzeit stimmt' }
        } catch {}
    } catch {
        Fehler 'Keine Verbindung zu microsoft.com - Internet/DNS gestoert (Punkt 4 behebt das meist).'
    }

    # Epic-Server erreichbar?
    try {
        Invoke-WebRequest -Uri 'https://launcher-public-service-prod06.ol.epicgames.com' -Method Head -UseBasicParsing -TimeoutSec 10 -ErrorAction Stop | Out-Null
        Ok 'Epic Games Server erreichbar'
    } catch {
        if ($_.Exception.Response) { Ok 'Epic Games Server erreichbar' }
        else { Warnung 'Epic Games Server nicht erreichbar (Firewall/Antivirus/DNS pruefen).' }
    }

    # Wichtige Dienste
    foreach ($d in 'msiserver','BITS','wuauserv','CryptSvc') {
        $s = Get-Service $d -ErrorAction SilentlyContinue
        if (-not $s) { continue }
        if ($s.StartType -eq 'Disabled') {
            Fehler "Dienst '$($s.DisplayName)' ist deaktiviert (Punkt 3 schaltet ihn wieder ein)."
        } else { Ok "Dienst '$($s.DisplayName)' ist verfuegbar" }
    }

    # Grafiktreiber
    Get-CimInstance Win32_VideoController | ForEach-Object {
        $datum = $_.DriverDate
        $alter = if ($datum) { ((Get-Date) - $datum).Days } else { 0 }
        $txt = "Grafikkarte: $($_.Name) - Treiber $($_.DriverVersion)"
        if ($alter -gt 365) { Warnung "$txt ist ueber $([int]($alter/365)) Jahr(e) alt -> Punkt 8" }
        else { Ok $txt }
    }

    # Neustart ausstehend?
    $ausstehend = (Test-Path 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Component Based Servicing\RebootPending') -or
                  (Test-Path 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\WindowsUpdate\Auto Update\RebootRequired')
    if ($ausstehend) { Warnung 'Windows wartet auf einen Neustart - Installationen scheitern bis dahin oft!' }

    # Autostart
    $auto = @(Get-CimInstance Win32_StartupCommand -ErrorAction SilentlyContinue)
    if ($auto.Count -gt 10) {
        Warnung "$($auto.Count) Programme starten automatisch mit Windows - das bremst. (Task-Manager > Autostart)"
    } else { Ok "$($auto.Count) Autostart-Programme" }
}

# --- 2. Aufraeumen ----------------------------------------------------------

function Aufraeumen {
    Titel '2) Aufraeumen - Platz schaffen'
    $vorher = (Get-PSDrive C).Free

    $ordner = @(
        $env:TEMP,
        "$env:WINDIR\Temp",
        "$env:LOCALAPPDATA\CrashDumps",
        "$env:LOCALAPPDATA\D3DSCache",
        "$env:LOCALAPPDATA\NVIDIA\DXCache",
        "$env:LOCALAPPDATA\NVIDIA\GLCache",
        "$env:LOCALAPPDATA\AMD\DxCache",
        "$env:WINDIR\SoftwareDistribution\Download"
    )
    Stop-Service wuauserv, bits -Force -ErrorAction SilentlyContinue
    foreach ($o in $ordner) {
        if (Test-Path $o) {
            Info "Leere $o"
            Get-ChildItem $o -Force -ErrorAction SilentlyContinue |
                Where-Object { $_.FullName -ne $Arbeit } |
                Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
        }
    }
    Start-Service bits, wuauserv -ErrorAction SilentlyContinue

    try { Clear-RecycleBin -Force -ErrorAction Stop; Ok 'Papierkorb geleert' } catch {}

    # Windows-eigene Datentraegerbereinigung (ohne Rueckfragen)
    Info 'Windows-Datentraegerbereinigung laeuft (kann ein paar Minuten dauern) ...'
    $key = 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\VolumeCaches'
    Get-ChildItem $key -ErrorAction SilentlyContinue | ForEach-Object {
        New-ItemProperty -Path $_.PSPath -Name StateFlags0099 -Value 2 -PropertyType DWord -Force -ErrorAction SilentlyContinue | Out-Null
    }
    Start-Process cleanmgr.exe -ArgumentList '/sagerun:99' -Wait -ErrorAction SilentlyContinue

    $nachher = (Get-PSDrive C).Free
    Ok ("Freigegeben: {0:N1} GB" -f (($nachher - $vorher) / 1GB))
}

# --- 3. Windows reparieren --------------------------------------------------

function Windows-Reparieren {
    Titel '3) Windows-Systemdateien und Dienste reparieren'

    foreach ($d in @{ msiserver='Manual'; BITS='Manual'; wuauserv='Manual'; CryptSvc='Automatic'; W32Time='Manual' }.GetEnumerator()) {
        $s = Get-Service $d.Key -ErrorAction SilentlyContinue
        if ($s -and $s.StartType -eq 'Disabled') {
            Set-Service $d.Key -StartupType $d.Value
            Ok "Dienst $($d.Key) wieder eingeschaltet"
        }
    }

    Info 'Windows Installer neu registrieren (fuer .msi-Dateien wie Epic Games) ...'
    Start-Process msiexec.exe -ArgumentList '/unregister' -Wait -WindowStyle Hidden
    Start-Process msiexec.exe -ArgumentList '/regserver'  -Wait -WindowStyle Hidden
    Ok 'Windows Installer registriert'

    Info 'DISM: Windows-Abbild reparieren (10-30 Minuten, bitte nicht abbrechen) ...'
    & DISM.exe /Online /Cleanup-Image /RestoreHealth
    if ($LASTEXITCODE -eq 0) { Ok 'DISM fertig' } else { Warnung "DISM endete mit Code $LASTEXITCODE" }

    Info 'SFC: Systemdateien pruefen und ersetzen (10-20 Minuten) ...'
    & sfc.exe /scannow
    Ok 'SFC fertig'

    Info 'Festplatte auf Fehler pruefen (nur lesen) ...'
    & chkdsk.exe C: /scan
    if ($LASTEXITCODE -ne 0) {
        Warnung 'Chkdsk hat Probleme gefunden.'
        if (Frage 'Reparatur beim naechsten Neustart einplanen?') {
            & fsutil.exe dirty set C: | Out-Null
            Ok 'Reparatur laeuft beim naechsten Neustart'
        }
    }
}

# --- 4. Internet & Downloads ------------------------------------------------

function Zeit-Und-TLS {
    Info 'Uhrzeit synchronisieren ...'
    Set-Service W32Time -StartupType Manual -ErrorAction SilentlyContinue
    Start-Service W32Time -ErrorAction SilentlyContinue
    & w32tm /config /manualpeerlist:"time.windows.com,0x9 pool.ntp.org,0x9" /syncfromflags:manual /update | Out-Null
    & w32tm /resync /force | Out-Null
    Ok "Uhrzeit: $(Get-Date -Format 'dd.MM.yyyy HH:mm')"

    Info 'TLS 1.2 fuer aeltere Programme einschalten ...'
    foreach ($p in 'HKLM:\SOFTWARE\Microsoft\.NETFramework\v4.0.30319',
                   'HKLM:\SOFTWARE\WOW6432Node\Microsoft\.NETFramework\v4.0.30319') {
        if (Test-Path $p) {
            Set-ItemProperty $p -Name SchUseStrongCrypto -Value 1 -Type DWord
            Set-ItemProperty $p -Name SystemDefaultTlsVersions -Value 1 -Type DWord
        }
    }
    Ok 'TLS 1.2 aktiv'
}

# Setzt das Netzwerk zurueck - danach kann die Verbindung bis zum Neustart wackeln,
# deshalb laeuft das bei "Alles" ganz am Ende.
function Netz-Zuruecksetzen {
    Info 'DNS-Cache leeren, Netzwerk zuruecksetzen ...'
    & ipconfig /flushdns | Out-Null
    & netsh winsock reset | Out-Null
    & netsh int ip reset  | Out-Null
    & netsh winhttp reset proxy | Out-Null
    Ok 'Netzwerk zurueckgesetzt (wirkt voll nach Neustart)'

    if (Frage 'Schnellen, zuverlaessigen DNS (Cloudflare 1.1.1.1 + Google 8.8.8.8) einstellen?') {
        Get-NetAdapter | Where-Object Status -eq 'Up' | ForEach-Object {
            Set-DnsClientServerAddress -InterfaceIndex $_.ifIndex -ServerAddresses '1.1.1.1','8.8.8.8'
            Ok "DNS gesetzt fuer $($_.Name)"
        }
    }

    # Proxy-Reste von Adware entfernen
    $ie = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings'
    if ((Get-ItemProperty $ie -ErrorAction SilentlyContinue).ProxyEnable -eq 1) {
        Warnung 'Ein Proxy ist eingetragen - das blockiert oft Downloads.'
        if (Frage 'Proxy ausschalten?') {
            Set-ItemProperty $ie -Name ProxyEnable -Value 0
            Ok 'Proxy ausgeschaltet'
        }
    }
}

function Internet-Reparieren {
    Titel '4) Internet und Downloads reparieren'
    Zeit-Und-TLS
    Netz-Zuruecksetzen
}

# --- 5. Spiele-Laufzeitbibliotheken -----------------------------------------

function Laufzeiten-Installieren {
    Titel '5) Spiele-Bausteine installieren (Visual C++, DirectX, .NET)'
    Info 'Fehlen die, starten viele Spiele und Programme gar nicht oder mit DLL-Fehler.'

    $pakete = @(
        @{ Name='Visual C++ 2015-2022 (64-Bit)'; Url='https://aka.ms/vs/17/release/vc_redist.x64.exe'; Arg='/install /quiet /norestart' },
        @{ Name='Visual C++ 2015-2022 (32-Bit)'; Url='https://aka.ms/vs/17/release/vc_redist.x86.exe'; Arg='/install /quiet /norestart' },
        @{ Name='DirectX (aeltere Spiele)';      Url='https://download.microsoft.com/download/1/7/1/1718CCC4-6315-4D8E-9543-8E28A4E18C4C/dxwebsetup.exe'; Arg='/Q' }
    )
    foreach ($p in $pakete) {
        $datei = Join-Path $Arbeit ([IO.Path]::GetFileName($p.Url))
        Info "Installiere $($p.Name) ..."
        if (Lade-Herunter $p.Url $datei) {
            $proc = Start-Process $datei -ArgumentList $p.Arg -Wait -PassThru
            # 0 = ok, 1638 = neuere Version schon da, 3010 = Neustart noetig
            if (@(0, 1638, 3010) -contains $proc.ExitCode) { Ok "$($p.Name) ist installiert" }
            else { Warnung "$($p.Name): Code $($proc.ExitCode)" }
        }
    }

    if (Hat-Winget) {
        foreach ($id in 'Microsoft.DotNet.DesktopRuntime.8', 'Microsoft.VCRedist.2013.x64', 'Microsoft.VCRedist.2013.x86',
                        'Microsoft.VCRedist.2012.x64', 'Microsoft.VCRedist.2010.x64') {
            Info "winget: $id"
            & winget install --id $id -e --silent --source winget --accept-package-agreements --accept-source-agreements | Out-Null
        }
        Ok 'Aeltere Visual-C++-Versionen und .NET installiert'
    } else {
        Warnung 'winget fehlt - aeltere Visual-C++/.NET-Pakete uebersprungen (Punkt 7 installiert winget).'
    }

    # .NET 3.5 brauchen viele aeltere Spiele
    $net35 = Get-WindowsOptionalFeature -Online -FeatureName NetFx3 -ErrorAction SilentlyContinue
    if ($net35 -and $net35.State -ne 'Enabled') {
        Info '.NET Framework 3.5 einschalten ...'
        Enable-WindowsOptionalFeature -Online -FeatureName NetFx3 -All -NoRestart -ErrorAction SilentlyContinue | Out-Null
        Ok '.NET 3.5 eingeschaltet'
    }
}

# --- 6. Epic Games Launcher -------------------------------------------------

function Epic-Reparieren {
    Titel '6) Epic Games Launcher reparieren / sauber neu installieren'

    Info 'Epic-Prozesse beenden ...'
    Get-Process EpicGamesLauncher, EpicWebHelper, UnrealCEFSubProcess -ErrorAction SilentlyContinue |
        Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2

    # Kaputte Zwischenspeicher sind der haeufigste Grund fuer weisse Fenster und haengende Downloads
    $saved = "$env:LOCALAPPDATA\EpicGamesLauncher\Saved"
    Get-ChildItem $saved -Directory -Filter 'webcache*' -ErrorAction SilentlyContinue |
        Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
    Ok 'Epic-Webcache geloescht'

    # Abgebrochene Installer-Reste
    Get-ChildItem "$env:USERPROFILE\Downloads" -Filter 'EpicInstaller*.msi' -ErrorAction SilentlyContinue |
        Where-Object { $_.Length -lt 50MB } | ForEach-Object {
            Remove-Item $_.FullName -Force
            Info "Kaputten Installer entfernt: $($_.Name)"
        }

    $installiert = Test-Path "${env:ProgramFiles(x86)}\Epic Games\Launcher\Portal\Binaries\Win64\EpicGamesLauncher.exe"
    if ($installiert) {
        Ok 'Epic Games Launcher ist installiert.'
        if (-not (Frage 'Trotzdem frisch drueberinstallieren (Spiele bleiben erhalten)?')) { return }
    }

    $freiGB = (Get-PSDrive C).Free / 1GB
    if ($freiGB -lt 5) {
        Fehler ("Nur {0:N1} GB frei auf C: - erst Punkt 2 (Aufraeumen) ausfuehren!" -f $freiGB)
        return
    }

    $msi = Join-Path $Arbeit 'EpicInstaller.msi'
    $ok = Lade-Herunter 'https://launcher-public-service-prod06.ol.epicgames.com/launcher/api/installer/download/EpicGamesLauncherInstaller.msi' $msi
    if (-not $ok -and (Hat-Winget)) {
        Info 'Versuche es ueber winget ...'
        & winget install --id EpicGames.EpicGamesLauncher -e --source winget --accept-package-agreements --accept-source-agreements
        return
    }
    if (-not $ok) { return }

    Unblock-File $msi -ErrorAction SilentlyContinue
    $log = Join-Path $Desktop 'Epic-Installation-Log.txt'
    Info 'Installiere Epic Games Launcher ...'
    $proc = Start-Process msiexec.exe -ArgumentList "/i `"$msi`" /qb /norestart /l*v `"$log`"" -Wait -PassThru
    switch ($proc.ExitCode) {
        0       { Ok 'Epic Games Launcher installiert! Startmenue > Epic Games Launcher.'; Remove-Item $log -ErrorAction SilentlyContinue }
        3010    { Ok 'Installiert - bitte PC neu starten.' }
        1618    { Fehler 'Eine andere Installation laeuft gerade. PC neu starten und nochmal versuchen.' }
        1603    { Fehler "Installation fehlgeschlagen (1603). Meist: alter Rest im Weg. Log: $log"
                  Warnung 'Tipp: Einstellungen > Apps > Epic Games Launcher deinstallieren, PC neu starten, Punkt 6 nochmal.' }
        default { Fehler "Installation endete mit Code $($proc.ExitCode). Log: $log" }
    }

    # Firewall-Freigabe, falls Antivirus/Firewall den Launcher blockt
    $exe = "${env:ProgramFiles(x86)}\Epic Games\Launcher\Portal\Binaries\Win64\EpicGamesLauncher.exe"
    if ((Test-Path $exe) -and -not (Get-NetFirewallRule -DisplayName 'Epic Games Launcher (PC-Doktor)' -ErrorAction SilentlyContinue)) {
        New-NetFirewallRule -DisplayName 'Epic Games Launcher (PC-Doktor)' -Direction Outbound -Program $exe -Action Allow | Out-Null
        Ok 'Firewall-Freigabe fuer Epic eingetragen'
    }
}

# --- 7. Downloads oeffnen koennen -------------------------------------------

function Downloads-Oeffnen {
    Titel '7) Heruntergeladene Dateien oeffnen und benutzen koennen'

    # Windows markiert Downloads als "aus dem Internet" -> blockiert/Warnung
    $dl = "$env:USERPROFILE\Downloads"
    $n = 0
    Get-ChildItem $dl -Recurse -File -ErrorAction SilentlyContinue | ForEach-Object {
        if (Get-Item $_.FullName -Stream Zone.Identifier -ErrorAction SilentlyContinue) {
            Unblock-File $_.FullName -ErrorAction SilentlyContinue; $n++
        }
    }
    Ok "$n Dateien im Download-Ordner entsperrt"

    # Dateizuordnungen fuer Programme/Installer reparieren (von Viren oft verbogen)
    Info 'Zuordnung fuer .exe / .msi / .bat pruefen ...'
    & cmd.exe /c 'assoc .exe=exefile' | Out-Null
    & cmd.exe /c 'assoc .msi=Msi.Package' | Out-Null
    & cmd.exe /c 'assoc .bat=batfile' | Out-Null
    & cmd.exe /c 'assoc .zip=CompressedFolder' | Out-Null
    Ok 'Dateizuordnungen repariert'

    if (-not (Hat-Winget)) {
        Info 'winget (Windows-Paketmanager) fehlt - wird installiert ...'
        $appx = Join-Path $Arbeit 'winget.msixbundle'
        if (Lade-Herunter 'https://aka.ms/getwinget' $appx) {
            try { Add-AppxPackage -Path $appx -ErrorAction Stop; Ok 'winget installiert' }
            catch { Warnung 'winget-Installation fehlgeschlagen - Microsoft Store > "App-Installer" aktualisieren.' }
        }
    }

    if (Hat-Winget) {
        Info 'Programme zum Oeffnen gaengiger Dateien installieren:'
        Info '  7-Zip (zip, rar, 7z), VLC (alle Videos/Musik), Adobe Reader (PDF)'
        if (Frage 'Installieren?') {
            foreach ($id in '7zip.7zip', 'VideoLAN.VLC', 'Adobe.Acrobat.Reader.64-bit') {
                Info "Installiere $id ..."
                & winget install --id $id -e --silent --source winget --accept-package-agreements --accept-source-agreements | Out-Null
            }
            Ok 'Fertig - .rar/.7z, Videos und PDFs lassen sich jetzt oeffnen'
        }
    }
}

# --- 8. Leistung fuer Spiele ------------------------------------------------

function Leistung {
    Titel '8) Leistung fuer Spiele verbessern'

    # Hoechstleistung als Energiesparplan
    & powercfg /setactive 8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c 2>$null
    if ($LASTEXITCODE -eq 0) { Ok 'Energieplan: Hoechstleistung' }

    # Spielmodus an, Xbox-Aufnahme im Hintergrund aus (frisst FPS)
    New-Item 'HKCU:\Software\Microsoft\GameBar' -Force -ErrorAction SilentlyContinue | Out-Null
    Set-ItemProperty 'HKCU:\Software\Microsoft\GameBar' -Name AutoGameModeEnabled -Value 1 -Type DWord
    Set-ItemProperty 'HKCU:\Software\Microsoft\GameBar' -Name AllowAutoGameMode -Value 1 -Type DWord
    New-Item 'HKCU:\System\GameConfigStore' -Force -ErrorAction SilentlyContinue | Out-Null
    Set-ItemProperty 'HKCU:\System\GameConfigStore' -Name GameDVR_Enabled -Value 0 -Type DWord
    Ok 'Spielmodus an, Hintergrundaufnahme aus'

    # Hardwarebeschleunigte GPU-Planung (wenn unterstuetzt)
    Set-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Control\GraphicsDrivers' -Name HwSchMode -Value 2 -Type DWord -ErrorAction SilentlyContinue
    Ok 'GPU-Planung aktiviert (wirkt nach Neustart, falls unterstuetzt)'

    # SSD trimmen / HDD defragmentieren
    Info 'Laufwerk C: optimieren (bei alter HDD kann das dauern) ...'
    Optimize-Volume -DriveLetter C -ErrorAction SilentlyContinue
    Ok 'Laufwerk optimiert'

    # Grafiktreiber
    $gpu = (Get-CimInstance Win32_VideoController | Select-Object -First 1).Name
    Info "Grafikkarte: $gpu"
    $seite = switch -Wildcard ($gpu) {
        '*NVIDIA*' { 'https://www.nvidia.com/de-de/drivers/' }
        '*AMD*'    { 'https://www.amd.com/de/support/download/drivers.html' }
        '*Radeon*' { 'https://www.amd.com/de/support/download/drivers.html' }
        '*Intel*'  { 'https://www.intel.de/content/www/de/de/support/detect.html' }
        default    { $null }
    }
    if ($seite -and (Frage 'Treiber-Downloadseite fuer deine Grafikkarte oeffnen?')) {
        Start-Process $seite
    }

    Info 'Autostart-Programme (im Task-Manager > Autostart abschalten, was du nicht brauchst):'
    Get-CimInstance Win32_StartupCommand -ErrorAction SilentlyContinue |
        ForEach-Object { Info "  - $($_.Name)" }
}

# --- 9. Viren-Schnellscan ---------------------------------------------------

function Virenscan {
    Titel '9) Viren-Schnellscan (Windows Defender)'
    try {
        Update-MpSignature -ErrorAction Stop
        Ok 'Virendefinitionen aktualisiert'
        Info 'Schnellscan laeuft (5-15 Minuten) ...'
        Start-MpScan -ScanType QuickScan -ErrorAction Stop
        $funde = @(Get-MpThreatDetection -ErrorAction SilentlyContinue)
        if ($funde.Count -gt 0) { Warnung "$($funde.Count) Bedrohung(en) gefunden - Windows-Sicherheit oeffnen und entfernen lassen." }
        else { Ok 'Nichts gefunden' }
    } catch {
        Warnung 'Windows Defender ist aus (anderes Antivirus aktiv?). Dort einen Scan starten.'
    }
}

# --- Ablauf -----------------------------------------------------------------

function Wiederherstellungspunkt {
    Info 'Lege Wiederherstellungspunkt an (falls etwas schiefgeht, kannst du zurueck) ...'
    try {
        Enable-ComputerRestore -Drive 'C:\' -ErrorAction SilentlyContinue
        Checkpoint-Computer -Description 'Vor PC-Doktor' -RestorePointType MODIFY_SETTINGS -ErrorAction Stop
        Ok 'Wiederherstellungspunkt "Vor PC-Doktor" erstellt'
    } catch {
        Warnung 'Kein Wiederherstellungspunkt (Windows erlaubt nur einen pro 24 Std.) - geht trotzdem weiter.'
    }
}

function Alles {
    Wiederherstellungspunkt
    Diagnose
    Titel 'Uhrzeit und sichere Verbindung (TLS) richten'
    Zeit-Und-TLS
    Aufraeumen
    Windows-Reparieren
    Laufzeiten-Installieren
    Downloads-Oeffnen
    Epic-Reparieren
    Leistung
    Virenscan
    Titel 'Netzwerk zuruecksetzen'
    Netz-Zuruecksetzen
    Titel 'FERTIG - bitte jetzt den PC NEU STARTEN!'
    Info "Bericht gespeichert: $Bericht"
}

if (-not (Ist-Admin)) {
    Fehler 'Bitte ueber PC-Doktor.bat starten (braucht Administratorrechte).'
    Read-Host 'Enter zum Beenden'
    exit 1
}

Start-Transcript -Path $Bericht -Append | Out-Null

while ($true) {
    Clear-Host
    Write-Host ''
    Write-Host '   ____   ____      ____        _    _              ' -ForegroundColor Cyan
    Write-Host '  |  _ \ / ___|    |  _ \  ___ | | _| |_ ___  _ __  ' -ForegroundColor Cyan
    Write-Host '  | |_) | |   _____| | | |/ _ \| |/ / __/ _ \| `__| ' -ForegroundColor Cyan
    Write-Host '  |  __/| |__|_____| |_| | (_) |   <| || (_) | |    ' -ForegroundColor Cyan
    Write-Host '  |_|    \____|    |____/ \___/|_|\_\\__\___/|_|    ' -ForegroundColor Cyan
    Write-Host ''
    Write-Host '   A) ALLES REPARIEREN (empfohlen, ca. 30-60 Minuten)' -ForegroundColor Green
    Write-Host ''
    Write-Host '   1) Diagnose - nur nachsehen, nichts aendern'
    Write-Host '   2) Aufraeumen - Speicherplatz freimachen'
    Write-Host '   3) Windows-Systemdateien reparieren'
    Write-Host '   4) Internet / abbrechende Downloads reparieren'
    Write-Host '   5) Spiele-Bausteine (Visual C++, DirectX, .NET)'
    Write-Host '   6) Epic Games Launcher reparieren / installieren'
    Write-Host '   7) Downloads oeffnen koennen (entsperren, 7-Zip, VLC ...)'
    Write-Host '   8) Leistung fuer Spiele'
    Write-Host '   9) Virenscan'
    Write-Host ''
    Write-Host '   N) PC neu starten        X) Beenden'
    Write-Host ''
    $wahl = (Read-Host '   Deine Wahl').Trim().ToUpper()
    switch ($wahl) {
        'A' { Alles }
        '1' { Diagnose }
        '2' { Aufraeumen }
        '3' { Wiederherstellungspunkt; Windows-Reparieren }
        '4' { Internet-Reparieren }
        '5' { Laufzeiten-Installieren }
        '6' { Epic-Reparieren }
        '7' { Downloads-Oeffnen }
        '8' { Wiederherstellungspunkt; Leistung }
        '9' { Virenscan }
        'N' { Stop-Transcript | Out-Null; Restart-Computer -Force; exit }
        'X' { Stop-Transcript | Out-Null; exit }
        default { Warnung 'Bitte A, 1-9, N oder X eingeben.' }
    }
    Write-Host ''
    Read-Host '  Enter fuer das Menue'
}
