# Run only after every verification driver process has finished.
$ErrorActionPreference = 'Stop'
$workspaceRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$clusterPath = Join-Path $workspaceRoot '.pr18_pgdata'
& 'C:\Program Files\PostgreSQL\18\bin\pg_ctl.exe' -D $clusterPath status
if ($LASTEXITCODE -ne 3) { throw 'Expected stopped disposable PostgreSQL server. Cleanup aborted.' }
Copy-Item -LiteralPath (Join-Path $workspaceRoot '.pr18_postgres.log') -Destination (Join-Path $PSScriptRoot 'pr18-postgres.log')
$temporaryNames = @('.pr18_baseline_addons','.pr18_odoo_data','.pr18_pgdata','.pr18_odoo.conf','.pr18_postgres.log','.pr18_runner.json','.pr18_state.json')
$verifiedTargets = @()
foreach ($temporaryName in $temporaryNames) {
    $candidate = Get-Item -LiteralPath (Join-Path $workspaceRoot $temporaryName) -Force
    if ((Split-Path -Parent $candidate.FullName) -ne $workspaceRoot) { throw 'Target escaped workspace.' }
    if ($candidate.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Refusing cleanup through a reparse point.' }
    $verifiedTargets += $candidate.FullName
}
Remove-Item -LiteralPath $verifiedTargets -Recurse -Force
Write-Output 'PR18_RUNTIME_CLEANUP=PASS seven exact disposable workspace targets removed after stopped-server status.'
