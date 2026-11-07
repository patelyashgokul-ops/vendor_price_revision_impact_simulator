# Verify stopped state and retain database/filestore under TESTING_POLICY.md:51.
$ErrorActionPreference = 'Stop'
$workspaceRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$clusterPath = Join-Path $workspaceRoot '.pr20_pgdata'
& 'C:\Program Files\PostgreSQL\18\bin\pg_ctl.exe' -D $clusterPath status
if ($LASTEXITCODE -ne 3) { throw 'Expected stopped disposable PostgreSQL server. Retention verification aborted.' }
Copy-Item -LiteralPath (Join-Path $workspaceRoot '.pr20_postgres.log') -Destination (Join-Path $PSScriptRoot 'pr20-postgres.log')
$temporaryNames = @('.pr20_baseline_addons','.pr20_odoo_data','.pr20_pgdata','.pr20_odoo.conf','.pr20_postgres.log','.pr20_runner.json','.pr20_state.json')
$verifiedTargets = @()
foreach ($temporaryName in $temporaryNames) {
    $candidate = Get-Item -LiteralPath (Join-Path $workspaceRoot $temporaryName) -Force
    if ((Split-Path -Parent $candidate.FullName) -ne $workspaceRoot) { throw 'Target escaped workspace.' }
    if ($candidate.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Unexpected runtime reparse point.' }
    $verifiedTargets += $candidate.FullName
}
$retentionEvidence = @{
    status = 'PASS'
    completed_at = [DateTime]::UtcNow.ToString('o')
    workspace = $workspaceRoot
    stopped_server_status = 3
    removed_paths = @()
    retained_paths = $verifiedTargets
    retention_reason = 'TESTING_POLICY.md:51 prohibits deleting databases; disposable cluster, filestore and reproduction configuration retained stopped.'
    postgres_log = 'evidence/pr20-postgres.log'
}
$retentionEvidence | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $PSScriptRoot 'pr20-runtime-disposition.json') -Encoding utf8
Write-Output 'PR20_RUNTIME_RETENTION=PASS server stopped, seven owned runtime paths retained; no databases deleted.'
