[CmdletBinding()]
param(
    [switch]$UpdateOnly
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$AppUrl = "http://127.0.0.1:8765/"
$HealthUrl = "http://127.0.0.1:8765/api/status"
$ExtensionDirectory = Join-Path $ProjectRoot "extension"
# Se conserva esta ruta histórica para no perder la sesión de Edge existente.
$EdgeProfileDirectory = Join-Path $env:LOCALAPPDATA "SwipeClean\EdgeProfile"
$LogDirectory = Join-Path $ProjectRoot "logs"
$LauncherLog = Join-Path $LogDirectory "launcher.log"
$ServerOutputLog = Join-Path $LogDirectory "server-output.log"
$ServerErrorLog = Join-Path $LogDirectory "server-error.log"

New-Item -ItemType Directory -Path $LogDirectory -Force | Out-Null

function Write-LauncherLog {
    param([string]$Message)
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Add-Content -LiteralPath $LauncherLog -Value "[$timestamp] $Message"
}

function Show-LauncherError {
    param([string]$Message)
    Write-LauncherLog "ERROR: $Message"
    $popup = New-Object -ComObject WScript.Shell
    $null = $popup.Popup("$Message`n`nDetalles: $LauncherLog", 0, "Photo Swipper Filter", 16)
}

function Test-SwipeClean {
    try {
        $response = Invoke-WebRequest -Uri $HealthUrl -UseBasicParsing -TimeoutSec 2
        return $response.StatusCode -eq 200
    }
    catch {
        return $false
    }
}

function Find-MicrosoftEdge {
    $candidates = @(
        (Join-Path ${env:ProgramFiles(x86)} "Microsoft\Edge\Application\msedge.exe"),
        (Join-Path $env:ProgramFiles "Microsoft\Edge\Application\msedge.exe"),
        (Join-Path $env:LOCALAPPDATA "Microsoft\Edge\Application\msedge.exe")
    )

    foreach ($candidate in $candidates) {
        if ($candidate -and (Test-Path -LiteralPath $candidate)) {
            return $candidate
        }
    }
    return $null
}

function Open-SwipeCleanBrowser {
    $edge = Find-MicrosoftEdge
    $manifest = Join-Path $ExtensionDirectory "manifest.json"

    if ($edge -and (Test-Path -LiteralPath $manifest)) {
        New-Item -ItemType Directory -Path $EdgeProfileDirectory -Force | Out-Null
        $arguments = @(
            "--user-data-dir=`"$EdgeProfileDirectory`"",
            "--load-extension=`"$ExtensionDirectory`"",
            "--no-first-run",
            "--no-default-browser-check",
            $AppUrl
        )
        Start-Process -FilePath $edge -ArgumentList $arguments
        Write-LauncherLog "Photo Swipper Filter abierto en el perfil dedicado de Edge con el asistente de Google Photos disponible."
        return
    }

    Write-LauncherLog "Edge o la extension no estan disponibles; se abre el navegador predeterminado sin asistente."
    Start-Process $AppUrl
}

function Invoke-GitSafeUpdate {
    if (-not (Test-Path (Join-Path $ProjectRoot ".git"))) {
        Write-LauncherLog "No es un repositorio Git; se omite la actualizacion."
        return
    }

    if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
        Write-LauncherLog "Git no esta instalado o no esta en PATH; se omite la actualizacion."
        return
    }

    Push-Location $ProjectRoot
    try {
        & git fetch --quiet origin 2>> $LauncherLog
        if ($LASTEXITCODE -ne 0) {
            Write-LauncherLog "No se pudo consultar GitHub; se inicia la version local."
            return
        }

        $changes = @(& git status --porcelain 2>> $LauncherLog)
        if ($LASTEXITCODE -ne 0 -or $changes.Count -gt 0) {
            Write-LauncherLog "Hay cambios locales; no se actualiza para no sobrescribirlos."
            return
        }

        $branch = (& git branch --show-current 2>> $LauncherLog).Trim()
        $upstream = (& git rev-parse --abbrev-ref --symbolic-full-name '@{u}' 2>$null)
        if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($upstream)) {
            & git show-ref --verify --quiet refs/remotes/origin/master
            $hasOriginMaster = $LASTEXITCODE -eq 0
            if ($branch -eq "master" -and $hasOriginMaster) {
                $upstream = "origin/master"
            }
            else {
                Write-LauncherLog "La rama '$branch' no tiene una rama remota asociada; se omite la actualizacion."
                return
            }
        }

        $behind = [int]((& git rev-list --count "HEAD..$upstream" 2>> $LauncherLog).Trim())
        $ahead = [int]((& git rev-list --count "$upstream..HEAD" 2>> $LauncherLog).Trim())

        if ($behind -eq 0) {
            Write-LauncherLog "GitHub no tiene actualizaciones nuevas."
            return
        }
        if ($ahead -ne 0) {
            Write-LauncherLog "La rama local y GitHub divergen; no se actualiza automaticamente."
            return
        }

        & git merge --ff-only $upstream 2>> $LauncherLog | Out-Null
        if ($LASTEXITCODE -eq 0) {
            Write-LauncherLog "Actualizacion de GitHub aplicada correctamente ($behind commit/s)."
        }
        else {
            Write-LauncherLog "Git no pudo aplicar la actualizacion; se conserva la version local."
        }
    }
    catch {
        Write-LauncherLog "Fallo al comprobar GitHub: $($_.Exception.Message). Se inicia la version local."
    }
    finally {
        Pop-Location
    }
}

function Initialize-PythonEnvironment {
    $venvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
    if (-not (Test-Path $venvPython)) {
        $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
        if (-not $pythonCommand) {
            throw "Python no esta instalado o no esta disponible en PATH."
        }
        Write-LauncherLog "Creando el entorno de Python por primera vez."
        & $pythonCommand.Source -m venv (Join-Path $ProjectRoot ".venv") 2>> $LauncherLog
        if ($LASTEXITCODE -ne 0) {
            throw "No se pudo crear el entorno de Python."
        }
    }

    $requirements = Join-Path $ProjectRoot "requirements-mvp.txt"
    $stamp = Join-Path $ProjectRoot ".venv\.requirements-mvp.sha256"
    $sha256 = [System.Security.Cryptography.SHA256]::Create()
    $requirementsStream = [System.IO.File]::OpenRead($requirements)
    try {
        $currentHash = [System.BitConverter]::ToString(
            $sha256.ComputeHash($requirementsStream)
        ).Replace("-", "")
    }
    finally {
        $requirementsStream.Dispose()
        $sha256.Dispose()
    }
    $installedHash = if (Test-Path $stamp) { (Get-Content -LiteralPath $stamp -Raw).Trim() } else { "" }

    if ($currentHash -ne $installedHash) {
        Write-LauncherLog "Instalando o actualizando dependencias."
        & $venvPython -m pip install --disable-pip-version-check -r $requirements 2>> $LauncherLog | Out-Null
        if ($LASTEXITCODE -ne 0) {
            throw "No se pudieron instalar las dependencias."
        }
        Set-Content -LiteralPath $stamp -Value $currentHash -NoNewline
    }

    return $venvPython
}

if ($UpdateOnly) {
    Invoke-GitSafeUpdate
    exit 0
}

try {
    Write-LauncherLog "Inicio solicitado."

    if (Test-SwipeClean) {
        Write-LauncherLog "El servidor ya estaba funcionando; se abre el navegador."
        Open-SwipeCleanBrowser
        exit 0
    }

    Invoke-GitSafeUpdate
    $python = Initialize-PythonEnvironment
    $application = Join-Path $ProjectRoot "mvp_app.py"

    Write-LauncherLog "Iniciando el servidor oculto."
    $server = Start-Process -FilePath $python `
        -ArgumentList @("`"$application`"") `
        -WorkingDirectory $ProjectRoot `
        -WindowStyle Hidden `
        -RedirectStandardOutput $ServerOutputLog `
        -RedirectStandardError $ServerErrorLog `
        -PassThru

    $ready = $false
    for ($attempt = 0; $attempt -lt 60; $attempt++) {
        if (Test-SwipeClean) {
            $ready = $true
            break
        }
        if ($server.HasExited) {
            break
        }
        Start-Sleep -Milliseconds 500
    }

    if (-not $ready) {
        throw "El servidor no respondio despues de 30 segundos."
    }

    Write-LauncherLog "Servidor verificado; abriendo $AppUrl"
    Open-SwipeCleanBrowser
}
catch {
    Show-LauncherError $_.Exception.Message
    exit 1
}
