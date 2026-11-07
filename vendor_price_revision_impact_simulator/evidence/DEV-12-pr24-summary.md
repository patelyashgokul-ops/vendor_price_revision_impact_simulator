# PR24 / DEV12 — financial and audit reporting checkpoint

Overall status: **IN_PROGRESS**, not VERIFIED. PR25 has not started. The
implementation and verified subset below do not close every PR24 acceptance item.
Final machine-readable evidence is in TEST_REPORT.json.pr24_handoff and the
source-bound history entries; older failures remain retained.

## A — Environment

Odoo 20.0 Community final, existing addon version 20.0.1.0.0 preserved. Official
stable baseline was checked at development start against https://nightly.odoo.com/.
Python 3.14.6 and PostgreSQL 18.4; installed XlsxWriter/openpyxl/pypdf. Native
renderer: wkhtmltopdf 0.12.6 with patched Qt. PDF visual review uses bundled
pypdfium2. No Enterprise component or core upgrade was introduced.

All runtime work uses explicitly owned synthetic databases. The original PR23
source is codex_vpr_pr23_upgrade_4_20261102. PR24 owns
codex_vpr_pr24_fresh_1_20261103, codex_vpr_pr24_fresh_2_20261103 and
codex_vpr_pr24_upgrade_1_20261103. No database was deleted.

## B — Implementation

One authorized canonical dataset serves HTML, native QWeb PDF, XLSX and CSV.
Seventeen fixed adapters cover revision comparison, financial/gross-profit,
product/vendor/customer/SO/supply exposure, alternatives/recommendations,
reconciliation, approvals, committed application, observations, incidents,
corrections and retained incident chronology. Explicit source selection avoids
silently mixing analytical versions. Filters and aggregation dimensions are
server-defined. Companies, currencies, snapshots, scenarios and demand classes
remain distinct. Missing full amounts remain null; no cross-unit quantity total.

The service reuses stored PR08–23 facts and the PR15 Decimal profitability
function. It never rebuilds operational source engines. Current freshness and live
approval validity are explicitly NOT_CHECKED. This is retained-fact reporting,
not full historical reconstruction. Scenario cost comes from PR17's authoritative
Decimal-string profit payload, not its legacy Float display field.

## C — Files

Five new business/test files: models/reporting.py, models/reporting_data.py,
security/reporting_security.xml, views/reporting_views.xml and
tests/test_reporting.py. Four integrations changed: manifest, model/test imports
and the foundation test's exact expected menu set. The other 144 PR23 source
files remain byte-identical. Additional evidence drivers, source ledgers, output
artifacts and docs/ADVANCED_FINANCIAL_AND_AUDIT_REPORTING.md document the work.

## D — Financial reference evidence

The genuine PR14/15 integration fixture has demand 200, existing stock 60 at100,
protected PO40 at100 and residual procurement100 at115. Reports reproduce:
baseline20,000; revised21,500; incremental1,500; net revenue28,000;
gross profit8,000→6,500; margins28.57142857%→23.21428571%; erosion5.35714286pp.
The repeated-source/grouping and weighted-margin tests reject double counting
and averaging percentages. Unknown cost does not become zero; losses are not
clamped. The109 arithmetic fixture yields20,900/7,100/25.35714286% and projected
600 improvement. That arithmetic fixture is distinct from a full PR17 business
reference workflow; the retained PR23 scenario output has its own traced basis.

## E — Outputs

evidence/pr24-output-results.json lists actual rows, PDF pages, readers, source
IDs, dataset fingerprints and SHA256/size for every generated PDF/XLSX/CSV.
The genuine retained-workflow output probe covers at least summary, financial,
gross profit, approval compliance, committed application and incident reports;
the final precision check additionally covers a genuine retained scenario.
evidence/pr24-reference.pdf is the separate200-unit financial integration fixture.
Page PNGs are retained for visual inspection. No HTML fallback counts as PDF.

Workbooks are parsed with openpyxl; CSVs with csv.DictReader. Native PDF bytes,
page presence and extracted content are verified. Export bound:50,000 inspected
rows and32MiB canonical detail; HTML/PDF bound:500 rows. No silent truncation.
Oversized detail cells are rejected; long metadata is explicitly split into parts.

## F — Security

Original active internal owner, currently selected authorized companies, report
role and original source permissions are checked for every generation/download.
Transport elevation from native signed field URLs is explicitly dropped before
reading sources. Revocation tests include that native binary-stream path.
Purchase is limited to procurement/audit categories; Finance/Director/Auditor
still require source access. Sales Managers receive a restricted PR11 sales-value
profile without supplier costs or margin-derived inference. Parameters alone are
retained in transient rows; financial files are not public Odoo attachments.

CSV neutralizes ASCII/Unicode leading whitespace/control formula prefixes in
text while retaining numeric negatives. XLSX disables formula/URL interpretation,
writes text explicitly, retains exact decimals separately and contains no macros.

## G — Tests and retained failures

Fresh-install milestone:40 actual tests PASS on source
dedb72bf8f59336e7c5c05304d204c1d48679f965621f6f9bd989a4371271379,
with no source change during that run. Subsequent focused checks bind later
presentation/precision/Unicode changes to their actual source hashes. Do not
describe the earlier40-test source as the final complete module verification.
Actual PR23 upgrade QUICK and preservation/output assertion groups are separate
units, never added to Odoo test counts. Final counts/log paths are in the JSON.

Retained failures: initial QWeb context table name too long; removed report_file
field absent in Odoo20; exact foundation menu expectation needed the new menu;
native PDF asset URLs unavailable under disabled HTTP; Odoo20 BinaryValue API;
formatter module name shadowed by the native report data argument; baseline
config's broad path replacement redirected its filestore. Each failure was
recorded and corrected. The invalid first cold baseline is not preservation proof.
Validated capture is evidence/pr24-cold-pr23-preservation-v2.json.

An earlier broad milestone executed53 tests:51 passed and two reporting formatter
errors failed. It also spans a later reporting-security source change. Its36
unchanged legacy regression passes are useful dependency evidence, not a final
53-test PASS claim. Full release/browser/report-concurrency suites are NOT_RUN.

Formatter-only benchmark:100/500/2,000/10,000/50,000 actual parsed rows.
At50,000: CSV16.2196s, XLSX73.3245s, validation52.1835s, traced peak321,802,056
bytes, with tracemalloc overhead. It is earlier-source formatter evidence;
source construction/ORM/concurrency/production qualification were excluded.

## H — Business safety and preservation

Actual PR23→PR24 preservation verifies100 original stored business models and all
16 original vendor evidence files,114,956 nonempty bytes, against immutable
SHA256 plus native SHA1/checksum and file size. The same hashes are checked after
report generation. Native supplier rules, PO/SO, stock and accounting records
are included in stored-data checks. Report modules contain no source create,
write, unlink, SQL mutation, commit or sudo-read calls. No report executes prices,
repricing, approval decisions, correction plans, incident resolution or messages.
Test setup operations and separately retained PR22 applications are synthetic
fixture history, not reporting side effects or production activity.

## I — Progress and remaining acceptance

PR24 remains IN_PROGRESS. Required remaining work includes complete source-issue
and confidence presentation across all adapters, full revision-to-execution
chronology, richer comparable-scenario presentation, friendly source/drill-down
UI, remaining category integration fixtures and real report concurrency tests.
Current-source freshness or immutable report retention must be deliberately
implemented if required beyond the clearly disclosed retained-fact mode.
Mandatory relevant failures cannot be waived; final history records identify
exact source hashes and superseded evidence. TEST_REPORT.json and
DEVELOPMENT_PROGRESS.md retain this status.

## J — PR25 handoff

PR25 is NOT_STARTED. Future consumers may reuse the canonical contract only
within its established role/source/company boundaries. Preserve source identity,
company/currency/snapshot/scenario/demand partitions, null completeness, ratios of
amount sums, projected-versus-realized meaning and the no-operational-mutation
invariant. No dashboard, KPI cards, charts, alert automation or deployment was
implemented in PR24.

## Final tested subset evidence

Final source: dd210be29e46fa8cbd7c57103485a1eaaa051e96d2268666ced0ab03f83639f5.
Current-source QUICK11, seven output assertion groups and two preservation groups
PASS with no source change during execution. TARGETED17 passed source2ae107f0;
fresh MILESTONE40 passed sourcededb72bf; their exact full hashes/log SHA256 values
remain in TEST_REPORT.json.pr24_handoff.gate_records. Do not conflate these sources.
The final seven reports have rows/pages respectively: summary1/1, financial4/3,
gross profit2/2, approval2/2, application1/1, incident1/1, scenario1/1. All21 output
files match their recorded SHA256/size. Structured audit appendices summarize
passing controls and reference full canonical/XLSX evidence without dumping JSON
into PDF pages. Selected multi-page financial/approval and scenario pages were
rendered and visually inspected. Both owned clusters are stopped.

Overall PR24 remains IN_PROGRESS for the concrete remaining scope in section I.
