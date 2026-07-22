[CmdletBinding()]
param(
    [int]$Attempts = 3,
    [switch]$IncludeCoverage
)

$ErrorActionPreference = 'Stop'
$Attempts = [Math]::Max(1, [Math]::Min($Attempts, 3))

function Invoke-ReadOnlyValidation {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$Executable,
        [Parameter(Mandatory = $true)][string[]]$Arguments,
        [string[]]$TransientPatterns = @(
            'connection refused',
            'connection reset',
            'database is locked',
            'temporarily unavailable',
            'timed out',
            'timeout',
            'process cannot access the file',
            'resource busy',
            'network is unreachable'
        )
    )

    for ($attempt = 1; $attempt -le $Attempts; $attempt++) {
        Write-Host "`n[$Name] attempt $attempt/$Attempts" -ForegroundColor Cyan
        $processStartFailure = $false
        try {
            $output = & $Executable @Arguments 2>&1 | Out-String
            $exitCode = $LASTEXITCODE
        } catch {
            $processStartFailure = $true
            $exitCode = 127
            $output = $_.Exception.Message
        }
        Write-Host $output
        if ($exitCode -eq 0) {
            Write-Host "[$Name] PASS" -ForegroundColor Green
            return
        }

        $isTransient = $processStartFailure
        foreach ($pattern in $TransientPatterns) {
            if ($output.IndexOf($pattern, [System.StringComparison]::OrdinalIgnoreCase) -ge 0) {
                $isTransient = $true
                break
            }
        }

        if (-not $isTransient -or $attempt -eq $Attempts) {
            throw "[$Name] failed with exit code $exitCode. Deterministic source/test failures are not hidden or modified by this script."
        }

        $delay = [Math]::Min(12, 2 * $attempt)
        Write-Warning "[$Name] transient environment failure detected; retrying in $delay second(s)."
        Start-Sleep -Seconds $delay
    }
}

# Read-only checks only. No --fix, git add, commit, push, delete, move, or source edit commands.
Invoke-ReadOnlyValidation -Name 'Dependency integrity' -Executable 'python' -Arguments @('-m', 'pip', 'check')
Invoke-ReadOnlyValidation -Name 'Ruff lint' -Executable 'ruff' -Arguments @('check', '.') -TransientPatterns @()
Invoke-ReadOnlyValidation -Name 'Ruff format check' -Executable 'ruff' -Arguments @('format', '--check', '.') -TransientPatterns @()
Invoke-ReadOnlyValidation -Name 'Python compile' -Executable 'python' -Arguments @('-m', 'compileall', '-q', 'app', 'scripts', 'tests') -TransientPatterns @()

if ($IncludeCoverage) {
    Invoke-ReadOnlyValidation -Name 'Pytest with coverage' -Executable 'pytest' -Arguments @('--cov=app', '--cov-report=term-missing', '--cov-fail-under=70')
} else {
    Invoke-ReadOnlyValidation -Name 'Pytest' -Executable 'pytest' -Arguments @()
}

Write-Host "`nAll requested read-only validation checks passed." -ForegroundColor Green
