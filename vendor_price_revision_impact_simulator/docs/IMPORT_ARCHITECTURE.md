# Supplier file intake — PR-05

This phase preserves source evidence and extracts **untrusted raw rows**. Extraction
does not map columns or products, validate prices, calculate exposure, approve
revisions or change vendor price rules. PR-06 structural review is documented separately in `IMPORT_VALIDATION_GUIDE.md`;
product resolution and commercial/financial workflows remain deferred.

## Upload and authorization

Use **Vendor Price Simulator → Import Price Files**, or **Import Supplier Price
File** on an authorized draft revision. Select the company/revision and CSV or
XLSX format. CSV encoding and delimiter are explicit choices; they are never
guessed. XLSX users can inspect worksheet names. A workbook containing multiple
sheets requires explicit selection of a visible sheet. A missing/hidden sheet
produces a selection error without accepting a persistent source.

Purchase Users upload for their own drafts; Purchase Managers can intake other
authorized company drafts. The server rechecks actual draft-edit rights, company
and vendor relationships on every action. Wizard defaults and XML domains confer
no authority. Company selection must be within the user's assigned, currently
selected companies. Cancellation/approval/application revision states cannot
receive intake. No sudo is used for upload, extraction, staging or policy lookup.

## Evidence and fingerprints

Each accepted source has a batch and a `vendor.price.revision.evidence` record.
Exactly one permanent original binary is stored as a standard `ir.attachment`
linked to that evidence, with the same company and no public flag or access token.
The wizard uses Odoo 20 `fields.Binary(attachment=False)` and reads
`BinaryValue.content`; it clears its temporary binary after acceptance.

The immutable metadata captures sanitized display filename (never a filesystem
path), detected format/MIME type, byte size, SHA-256 of the **original bytes**,
uploader/time, revision/vendor/company and batch. The older `checksum` field
remains unverified manual metadata; `sha256_digest` is the generated fingerprint.
Corrected sources create new evidence/batches. Renaming does not change a digest;
the same filename with changed content receives a different digest.

Evidence/attachment replacement, company reassignment, public sharing, token
creation, copying and deletion are denied through ordinary ORM operations. A
private attachment creation method first checks revision authorization and then
calls the normal attachment ORM under that same user. A metadata-only elevated
lookup identifies protected attachments for guarding ID attacks; it never reads
or serves file content. Actual reads/downloads use the requesting user's access.
The normal authenticated Odoo content endpoint is reused; no public controller or
token-based download route is added. Technical superusers retain framework powers.

## Parsing and limits

CSV uses Python `csv.reader`, strict decoding/quoting and explicit UTF-8/BOM,
Windows-1252 or BOM-marked UTF-16. Delimiters are comma, semicolon or tab; quote
character is double quote. Quoted delimiters and multiline records are preserved.
Leading zeros, Unicode and price-like values remain text. Formula-like prefixes
`=`, `+`, `-`, `@` are untrusted strings and cause a review marker. Nothing executes.
Unknown encoding/delimiter requires correction; there is no lossy fallback or
automatic dialect guessing. Incorrect business column meanings belong to PR-06.

XLSX uses installed openpyxl 3.1.2, read-only, `data_only=False`, `keep_links=False`,
and explicit workbook closing. openpyxl and lxml are declared Python packaging
dependencies. No additional package was installed. The installed environment has
lxml 6.0.2 and no defusedxml, so **every XML/rels part** is preflighted with a bounded
lxml parser that disables entity resolution, DTD loading, network access and huge
trees; all DTD declarations are rejected, including UTF-16 XML declarations.
The [openpyxl security guidance](https://openpyxl.readthedocs.io/en/stable/)
and [read-only lifecycle](https://openpyxl.readthedocs.io/en/stable/optimized.html)
inform this explicit XML gate and resource cleanup.

The archive gate checks actual OOXML workbook structure/content type, member
names/count, aggregate expanded size, compression ratio/method, encrypted flags,
macros/embedded programs, external relationships, text lengths and actual cell
coordinates. Each part is read in bounded chunks. Validated XML bytes are copied
into a temporary **in-memory** ZIP with trustworthy size metadata before
openpyxl sees it. This parsing container is never the retained evidence or hash
source. No archive member is extracted to disk, no Excel process is invoked and
no formula/external link is evaluated. Format checks reject XLS/XLSM/XLSB/ODS/PDF,
generic ZIP, encrypted/unsupported workbooks and obvious executable/binary files.

Administrators can set company-specific technical limits under **Configuration →
Intake Resource Limits**. In the absence of a company override, safe technical
defaults apply; this is separate from commercial/financial policy setup.

| Limit | Default | Supported administrator bounds |
|---|---:|---:|
| Upload size | 10 MiB | 1–25 MiB |
| Extracted data rows | 10,000 | 1–20,000 |
| Columns | 100 | 1–200 |
| Characters per cell | 16,384 | 32–32,768 |
| ZIP expanded content | 64 MiB | 1–128 MiB |
| ZIP members | 256 | 8–1,024 |
| Compression ratio | 200 | 10–500 |
| Cooperative parse/staging time budget | 20 s | 1–60 s |

Additional hard caps: header selection 0–100; scanned rows/positions at most data
row limit + 1,000; JSON per staged row 256 KiB; total staged JSON 64 MiB. Standard
CSV parser field limits may reject oversized quoted fields before the custom
cell limit. XLSX dimensions are not trusted; actual cells are checked and
read-only dimensions reset. These bounds apply to all workbook parts, even when
only one sheet is selected. The time budget is checked between bounded operations;
it is not an external process watchdog. Normal Odoo worker/request limits remain
applicable. No claim of measured peak memory or universal throughput is made.

## Rows, headers and traceability

`vendor.price.revision.import.row` stores ordered `raw_cells` JSON arrays of
`{"value": ..., "type": ...}` primitives, source position, column count, formula
column indexes and `raw`/`review` extraction status. CSV empty cells are `""` text;
XLSX blanks are null with type `blank`, zero is numeric zero, dates become ISO
text with type `date`, booleans remain booleans, and formulas retain their literal
text with type `formula`. No arbitrary Python objects are stored/deserialized.

Headers use the same ordered primitive-cell structure and retain duplicate names.
Automatic header means the first nonblank row; an explicit header uses source
logical/worksheet row numbers. Nonblank preamble rows are counted separately.
Whitespace-only rows are skipped; counters distinguish logical records, preamble,
header, skipped blanks, extracted rows and warnings. Empty/header-only files never
report meaningful extraction success. Original source bytes remain authoritative.

CSV `source_row` is a logical record ordinal; `physical_start`/`physical_end`
track physical lines, including quoted multiline cells. XLSX positions are actual
worksheet row numbers. Formatting-only trailing XLSX cells are trimmed and rows
are padded to the header width with null blanks; original formatting is not
interpreted as supplier data. Selected sheet name/index and available names are
retained. Batch/source-row SQL uniqueness protects repeated supplier SKU rows
without treating product codes as unique identities.

## Lifecycle, duplicates and recovery

- `uploaded`: original evidence preserved, no completed extraction.
- `extracting`: technical attempt in progress.
- `extracted`: raw rows staged successfully, no business validation implied.
- `extraction_failed`: no partial rows retained; inspect controlled error code.
- `duplicate_review`: exact digest candidate within authorized visible scope;
  source is retained, rows are not extracted and PR-06 review is required.
- `cancelled`: evidence/history retained, no further extraction allowed.

Duplicate comparison uses company, vendor and original SHA-256 among batches the
current user is authorized to read. An ordinary preparer is not told about another
preparer's private revision. Managers see candidates throughout their authorized
company scope. No foreign company information or unauthorized revision ID is
returned. Filename is not a duplicate key. Corrected files are distinct sources.

Wizard row locking makes double-click acceptance idempotent. Company serialization
covers duplicate checks across revisions; batch row locking serializes extraction,
retry and cancellation. No-op row updates force stale repeatable-read competitors
to retry with a fresh transaction. A completed batch returns without creating
another attempt or row. Cancelled/duplicate-review batches cannot extract.

Parsing and ORM row creation occur inside a savepoint, with chunks of 250 ORM
rows. A controlled parse/resource/database failure rolls back all partial rows
and records a safe failure status plus an immutable attempt. The original source
remains. Failed-batch encoding/delimiter/worksheet/header options can be corrected
by an authorized draft preparer before retry. Every attempt retains its options,
limits, actor, timestamps and outcome. Prior errors are never erased. Errors do
not include supplier cells, raw parser messages, SQL, filesystem paths or secrets.

There are no intermediate business commits. An interrupted request rolls back its
uncommitted attempt; an already committed uploaded/failed batch remains retryable.
This synchronous phase creates no background queue or extraction cron. Transient
serialization failures must use normal Odoo transaction retry, never force success.

## Confidentiality and PR-06 handoff

Purchase Users read their own batches/rows/attempts, and manager/confidential-reader
roles read their authorized companies. Only draft-authorized purchase preparers
mutate intake through controlled actions. Auditors/Finance/Directors/Pricing
Operators read only. Sales-only, Configuration-only, unrelated internal, portal
and public users have no raw file/staging permission. Configuration Administrators
manage resource limits without gaining raw file access. ID-only reads, exports,
grouped queries and attachment content requests preserve company/role restrictions.
Standard Odoo export permissions are additionally required. No notifications or
new scheduling jobs are created.

PR-06 can consume extracted batches, immutable headers/raw cells, formula markers,
source/sheet/line references, duplicate-review state and safe technical errors.
It must add separate business mapping/validation results, preserve the immutable
source and raw rows, respect ownership/company/attachment access, and retain failed
attempts. It must never equate extracted rows with validated prices or directly
write live vendor rules. New final revision lines require later controlled phases.

## Focused performance plan

Generate synthetic 10/100/500/2,000/10,000-row CSV and XLSX sources without supplier
data. Check exact counts, hash/evidence stability, limits, no duplicate rows and
atomic retry, then measure wall time and peak process memory on a dedicated test
database. The current automated suite measures one 500-row CSV intake and reports
its actual local duration in the test log. Other dataset sizes and peak memory
remain NOT_MEASURED unless execution evidence explicitly says otherwise. A
configured 10,000-row limit is not proof of a measured 10,000-row workload.
