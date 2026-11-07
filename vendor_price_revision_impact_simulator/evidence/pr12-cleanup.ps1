# Run only after every verification driver process has finished.
$ErrorActionPreference = 'Stop'
$workspaceRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$clusterPath = Join-Path $workspaceRoot '.pr12_pgdata'
& 'C:\Program Files\PostgreSQL\18\bin\pg_ctl.exe' -D $clusterPath status
if ($LASTEXITCODE -ne 3) { throw 'Expected stopped disposable PostgreSQL server. Cleanup aborted.' }
Copy-Item -LiteralPath (Join-Path $workspaceRoot '.pr12_postgres.log') -Destination (Join-Path $PSScriptRoot 'pr12-postgres.log')
$temporaryNames = @('.pr12_baseline_addons','.pr12_odoo_data','.pr12_pgdata','.pr12_odoo.conf','.pr12_postgres.log','.pr12_runner.json','.pr12_state.json')
$verifiedTargets = @()
foreach ($temporaryName in $temporaryNames) {
    $candidate = Get-Item -LiteralPath (Join-Path $workspaceRoot $temporaryName) -Force
    if ((Split-Path -Parent $candidate.FullName) -ne $workspaceRoot) { throw 'Target escaped workspace.' }
    if ($candidate.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Refusing cleanup through a reparse point.' }
    $verifiedTargets += $candidate.FullName
}
Remove-Item -LiteralPath $verifiedTargets -Recurse -Force
Write-Output 'PR12_RUNTIME_CLEANUP=PASS seven exact disposable workspace targets removed after stopped-server status.'
