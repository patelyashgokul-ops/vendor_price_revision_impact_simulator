# PR24 advanced financial and audit reporting

Status: IN_PROGRESS. This document describes the implemented initial contract;
it is not acceptance evidence. PR25 has not started.

`models/reporting.py` defines seventeen fixed report adapters. The transient
wizard accepts an explicit set of at most 100 source snapshot/run IDs, selected
companies and an optional inclusive local date interval. The adapter defines the
source model, detail relationship, fields and timestamp; callers cannot provide
models, domains, SQL, ordering or arbitrary field names. IANA timezone conversion
uses the next local midnight as the exclusive end, including daylight saving.

All outputs obtain the same canonical dataset from `_dataset()`. Ordinary
previews and downloads persist parameters only, not financial results or public
attachments. A download recomputes the dataset under the active original owner
and rechecks reporting roles, selected companies and native source record access.
The QWeb context independently performs these checks for direct render requests.
Expired transient records are unavailable. There are no public bearer tokens.

Finance, Director and Auditor roles may request financial categories, subject to
source access. Purchase Managers may request procurement/audit categories.
Sales Managers receive a restricted PR11 commercial profile for customer and
sales-order exposure: tax-excluded sales values, outstanding quantities, source
currencies/units and protection classification. That profile contains no supplier
costs, gross profit, margin or cost-derived aggregates. A role grants no additional
source access. The dataset explicitly drops elevated transport authority before
source reads, including native signed binary-field URLs.

Product, vendor, customer, demand-class and financial grouping filters are fixed
server-defined options. Unsupported filter/report combinations raise a clear
validation error. Exact source versions remain distinct in grouped totals.

The current mode is **retained source facts**. `freshness=NOT_CHECKED` is explicit.
No report reconstructs historical live state or asserts current approval validity.
No monitoring, application, financial rebuild or approval action is invoked.
Only committed `VERIFIED` execution receipts are included in application reports;
plans and decisions are not application events. Raw execution keys are excluded.
Approval context exposes recorded makers, submitters, decision actors/principals,
stage assignments/quorums, policy versions and validity/invalidation timestamps.
It does not treat activities as decisions or recalculate live authority.
Applied-price context includes actual create/update/no-change counts, operator,
verification instant, approval/plan references and before/after fingerprints.
Scenario alternatives expose their exact baseline/version, source controls and
issues without ranking them. Recommendation context includes required revenue,
revenue gap, supplier ceiling, completeness and eligibility controls.

Margin totals use the existing PR15 Decimal profitability function. They group
by company, currency, exact source snapshot, scenario and demand class. Missing
amounts null the full total; the complete subset and excluded line count remain
visible. Duplicate source lines raise an error. Percentages are ratios of summed
amounts; erosion is percentage points. Quantities are never grand-totalled across
units. Alternatives and snapshot versions have no additive grand total.

CSV uses UTF-8 with BOM and `csv.writer`. Leading whitespace/control characters
cannot hide formula prefixes in text. Numeric negative values retain their sign.
XLSX uses XlsxWriter with formula/URL interpretation disabled, explicit string and
numeric cells, frozen headers and filters. Exact decimal strings accompany Excel
double-precision numbers in a separate sheet. Workbooks contain metadata and
limitations. The native Community QWeb action uses an independently authorized
context and the installed wkhtmltopdf 0.12.6 patched-Qt renderer.

Limits are 50,000 inspected detail rows, 32 MiB of canonical detail and 500 rows
for HTML/PDF. Oversized requests
raise actionable errors; no partial report is silently presented as complete.
These bounds are policy limits, not measured production capacity qualifications.
Metadata strings larger than Excel's cell limit are numbered into ordered parts;
oversized detail cells are rejected. No detail value is silently truncated.

Native PDF formatting uses a dedicated A4 paper format, repeated header/footer
and page numbers, currency-rounding display and four-decimal percentage/pp
display. Exact canonical amounts remain in the dataset and XLSX exact-value sheet.
Recorded instants are UTC; the selected IANA timezone governs date filtering.
Generation time is presentation metadata excluded from logical fingerprints.

`evidence/pr24-format-benchmark.json` records genuine CSV and XLSX generation plus
full-row parsing at 100/500/2,000/10,000/50,000 rows. At 50,000 rows, with
tracemalloc overhead, CSV took 16.2196 seconds, XLSX 73.3245 seconds, validation
52.1835 seconds and traced Python peak was 321,802,056 bytes. Source construction
and ORM queries were excluded. This is an earlier-source formatter benchmark,
not production/source-query/concurrency qualification.

## Outstanding acceptance work

Runtime and output evidence is recorded in TEST_REPORT.json, never inferred from
this document. Remaining acceptance scope includes friendly source selection and
drill-down UI, comprehensive completeness/issue adapters, optional current-source
freshness checks and immutable retained report evidence, fuller scenario
comparability presentation, revision-to-execution chronology (the current history
adapter reports retained incident events), all source category runtime fixtures,
real report concurrency checks and broader category integration evidence. Fresh
installation passed a40-test milestone on its recorded source version; the actual
PR23 upgrade preserved100 stored models and all16 source files. Later presentation
changes have separate final-source PDF/output and QUICK evidence. Source/role
revocation and signed binary-transport denial are covered by dedicated tests;
check their actual current-source results in TEST_REPORT.json.
These items must be resolved before PR24 can be marked VERIFIED.

PR25 may reuse the canonical contract only after these acceptance gates pass.
It must preserve company/currency/snapshot/demand partitions, source permissions,
null completeness, traceable IDs and the no-operational-mutation invariant.
