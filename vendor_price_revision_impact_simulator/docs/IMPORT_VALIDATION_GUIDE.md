# Import structural review — PR-06

PR-06 interprets source columns, checks lexical structure and preserves review
evidence. **Structurally ready** means neither product resolved (PR-07), commercial
price normalized (PR-08), financially verified, approved nor ready to apply.
No live vendor, customer, sales, purchase, stock or accounting writes occur.

## Mapping and preview

Open an extracted **Import Session**. Its original headers and raw rows remain
immutable. On **Column Mapping**, select one-based column ordinals and canonical
targets. Duplicate/blank header names are legal: ordinal, source batch/sheet and
the original header determine identity. The same source column cannot map to two
targets; a single-value target cannot take two columns. Missing/out-of-range and
unsupported mappings fail server-side. No automatic matching or template reuse
is attempted. Saved mappings are batch/vendor/company specific.

Supported targets: supplier code (`vendor_product_code`), supplier description
(`vendor_product_name`), other product identifier (`product_identifier_raw`),
`proposed_price_raw`, `currency_raw`, `purchase_uom_raw`, `min_qty_raw`,
`effective_date_raw`, `supplier_reference_raw`, `notes_raw`.

At least one identifier/description mapping is required. Price, currency, UoM,
MOQ and effective date must be explicitly mapped. Currency/date may instead use
the corresponding **explicit revision inheritance** checkbox. Missing mapped
values never silently fall back. A mapped field and its inheritance option may
not both be selected. Inherited results retain `REVISION_HEADER` provenance;
source values retain `FILE_COLUMN`, column/header/type/sheet; corrected values
retain `CORRECTION` and its evidence ID. Missing quantity is blocked: PR-06 does
not invent a quantity default without a future explicit company policy. No price
or UoM default is supported. Conservative zero-price review is mandatory here.

Disable a mapping rather than deleting it. Disabled definitions reserve their
ordinal/target identity; edit that definition to move it. Mapping/settings changes
append immutable full input snapshots with actor/time/version. Validation runs
also capture mapping and context, preserving prior interpretation. Reusable
templates are deferred. Configuration-only users have no confidential source
access or mapping authority; mappings require the existing draft-preparer rights.

## Lexical rules

Surrounding whitespace is removed from mapped source text only; corrections retain
the explicitly entered working text and must satisfy the selected syntax. Original raw values
and bytes remain intact. Leading zeros, Unicode, internal whitespace, punctuation
and case remain significant. Identifier/candidate fields are limited to 256
characters; descriptions and notes to 4,000. Unexpected controls, boolean values
and formula cells cannot become silently verified numeric prices.

Numbers are parsed with Decimal, never primary float conversion. Plain format
accepts `115`, `115.00`, `0.95`. Explicit alternatives support comma grouping/dot
decimal (`1,150.50`), dot grouping/comma decimal (`1.150,50`), or space grouping/comma
decimal (`1 150,50`). No ambiguous separator guessing occurs. NaN, Infinity,
exponents and malformed/negative prices or quantities are blocked. Blank is missing;
numeric/text zero is an explicit price candidate requiring review. Values remain
decimal strings; no currency rounding or normalization is performed.

Date format is explicitly ISO, DD/MM/YYYY or MM/DD/YYYY. Slash dates under ISO
require review rather than guessed interpretation. Impossible dates are blocked.
Typed XLSX dates already use ISO representations and retain their type provenance.
Currency requires exactly three uppercase letters; `ZZZ` can be structurally
well-formed even though PR-08 must check Odoo currency support/FX. UoM is source
text only: no unit resolution, conversions or tier applicability checks occur.

Formula/boolean source types and formula-like text beginning `=`, `+` or `@` require
review; invalid numeric formulas also have lexical errors. Negative numeric text
is assessed under the negative price/quantity rule. No uploaded expression runs.
There is no custom error-export/reporting feature. Normal authorized ORM exports
of review records escape text starting with spreadsheet formula prefixes at the
output boundary, without mutating original/corrected evidence. Standard Odoo export
permission is independently required.

## Duplicates and statuses

Within one batch, effective values form duplicate keys across **all supported
mapped canonical fields**, including identifiers/description, price, currency,
UoM, MOQ, date, references and notes. Decimal-equivalent numbers/date syntax and
surrounding whitespace normalize lexically for comparison. Internal punctuation,
case, terms, tiers and currencies remain significant. No SKU-only key or random
first-row acceptance is used. Duplicate issues identify source row positions;
all affected rows require review unless already blocked. Excluding or correcting
a row recomputes the group on revalidation. PR-05 exact-file SHA256 review remains
unchanged; duplicate-review source files are not silently re-extracted here.

Row statuses: pending_mapping, pending_validation, structurally_ready, needs_review,
blocked, excluded. Errors block; review_required issues also block advancement;
warnings are nonblocking. Structured issue codes include MISSING_REQUIRED_VALUE,
INVALID_PRICE_FORMAT, NEGATIVE_PRICE, ZERO_PRICE_REVIEW, INVALID_QUANTITY_FORMAT,
INVALID_CURRENCY_TEXT, MISSING_UOM_TEXT, INVALID_DATE_FORMAT,
AMBIGUOUS_DATE_FORMAT, EXCESSIVE_FIELD_LENGTH, UNSUPPORTED_CELL_VALUE,
MANUAL_REVIEW_REQUIRED and DUPLICATE_ROW_CANDIDATE. Mapping problems are shown
at batch level before producing row validation snapshots. Messages are bounded
and do not expose stack traces, paths, SQL or complete confidential files.

**Review Source Rows** opens normal paginated list/form views with Ready, Blocked,
Needs Review, Excluded, Corrected and Duplicate filters. Row detail separates raw
and effective values, issues, current result and correction history. Historical
results retain values/provenance/parsed candidates and duplicate source positions.
No Apply or Approve action is present.

## Corrections, exclusion and revalidation

Use a row's **Correct / Exclude / Reinstate** action. Corrections accept only
allowlisted canonical fields and bounded text, with a required 1–500 character
reason. Each append-only event preserves original source value, previous effective
value, new value, actor, time and version. Multiple corrections retain full ordered
history. Canonical overlays remain attached to that target if its source column
is later remapped; historical original values remain traceable in each event.
An identical effective-value submission is a no-op, not a fabricated audit event.

Exclusion/reinstatement also requires a reason and appends history. Excluded rows
remain visible and are never counted as structurally ready or returned downstream.
Mapping edits, settings edits, corrections, exclusions, reinstatement and inherited
revision-date changes increment the batch input version and clear current results
immediately. Old issues remain historical (`is_current=False`); no stale ready
status is retained. Whole-batch revalidation is deliberate: one correction can
alter duplicate groups elsewhere in the batch. Original XLSX/CSV is not reparsed.

**Validate Structure** serializes on the existing batch lock, snapshots inputs,
computes effective rows and duplicate groups, and stages an identifiable immutable
result set inside one savepoint. Current results/counters are published only after
all rows succeed. Failure leaves an honest failed run and pending row status;
no partial current snapshot survives. Worker interruption rolls back the request.
Serialization/deadlock exceptions propagate for Odoo's fresh-transaction retry.
No business method manually commits. Repeating validation with identical inputs
returns the existing completed snapshot without duplicating issues/corrections.

## Counters and security

For current results, staged rows reconcile to ready + blocked + needs review +
excluded + pending. Multiple errors in a row count as one blocked row. Issue totals
are separate and can exceed affected row counts. Stale inputs clear current issue
and ready counts. All-excluded/all-blocked/zero-ready batches never claim readiness
for product resolution. Extraction state remains `extracted`; validation state is
a separate field (mapping incomplete, pending, stale, failed, review required or
structural validation complete).

Purchase Users review their own accessible drafts; Purchase Managers review company
drafts. Finance/Auditor/Director/Pricing roles retain authorized read-only access.
Sales-only, portal/public, unrelated and Configuration-only users cannot read raw
review evidence. Separate roles compose only within mandatory selected authorized
company scope. New child models derive company from batch, refuse reassignment,
retain history and enforce direct read/export/grouped-query boundaries. Nested
commands can edit only that batch's mapping; raw rows and historical results
cannot be forged through public ORM or context defaults. Ordinary review does not
use sudo. Original attachment guards and authenticated downloads remain unchanged.

## Handoff and performance

PR-07 should call `batch.get_structurally_ready_rows()` in the normal authorized
environment; it fails if current input context does not match its snapshot.
Consume each row's current immutable result, effective values, parsed lexical
candidates and provenance. This does not resolve a product or prove commercial
applicability; PR-07/08 must produce separate results and retain source/history.

Mapping definitions and correction lists are prefetched once per run; duplicate
grouping uses in-memory keys rather than per-row product/database lookups. UI lists
paginate. Whole-batch invalidation is conservative for duplicate correctness.
The synthetic 500-row test intentionally generates 480 structurally ready, 12
blocked and 8 review rows, with unknown SKUs and well-formed unsupported currency
text to prove product/FX resolution is deferred. Actual timing belongs to retained
logs. Other 10/100/2,000/10,000 benchmark sizes and peak memory are NOT_MEASURED
unless later evidence explicitly records them.


## Technical records

All names below start with `vendor.price.revision.import.`:

| Suffix | Purpose |
|---|---|
| `mapping` | Guarded batch column ordinal/target definitions |
| `validation.run` | Immutable input/mapping snapshot and technical outcome |
| `validation.result` | Immutable per-row effective/provenance/lexical result |
| `issue` | Structured severity/code/message tied to one result version |
| `correction` | Append-only correction, exclusion and reinstatement evidence |
| `review.event` | Mapping/settings input-version history |
| `review.wizard` | Transient authorized correction/exclusion interface |

The existing `batch` and `row` records are extended rather than replaced. Original
raw-cell and evidence storage from PR-05 remains authoritative and immutable.
