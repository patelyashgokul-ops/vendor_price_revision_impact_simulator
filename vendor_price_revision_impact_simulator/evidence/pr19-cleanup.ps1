# Run only after every verification driver process has finished.
$ErrorActionPreference = 'Stop'
$workspaceRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$clusterPath = Join-Path $workspaceRoot '.pr19_pgdata'
& 'C:\Program Files\PostgreSQL\18\bin\pg_ctl.exe' -D $clusterPath status
if ($LASTEXITCODE -ne 3) { throw 'Expected stopped disposable PostgreSQL server. Cleanup aborted.' }
Copy-Item -LiteralPath (Join-Path $workspaceRoot '.pr19_postgres.log') -Destination (Join-Path $PSScriptRoot 'pr19-postgres.log')
$temporaryNames = @('.pr19_baseline_addons','.pr19_odoo_data','.pr19_pgdata','.pr19_odoo.conf','.pr19_postgres.log','.pr19_runner.json','.pr19_state.json')
$verifiedTargets = @()
foreach ($temporaryName in $temporaryNames) {
    $candidate = Get-Item -LiteralPath (Join-Path $workspaceRoot $temporaryName) -Force
    if ((Split-Path -Parent $candidate.FullName) -ne $workspaceRoot) { throw 'Target escaped workspace.' }
    if ($candidate.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Refusing cleanup through a reparse point.' }
    $verifiedTargets += $candidate.FullName
}
Remove-Item -LiteralPath $verifiedTargets -Recurse -Force
Write-Output 'PR19_RUNTIME_CLEANUP=PASS seven exact disposable workspace targets removed after stopped-server status.'

$cleanupEvidence = @{
    status = 'PASS'
    completed_at = [DateTime]::UtcNow.ToString('o')
    workspace = $workspaceRoot
    stopped_server_status = 3
    removed_paths = $verifiedTargets
    postgres_log = 'evidence/pr19-postgres.log'
}
$cleanupEvidence | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $PSScriptRoot 'pr19-runtime-cleanup.json') -Encoding utf8
