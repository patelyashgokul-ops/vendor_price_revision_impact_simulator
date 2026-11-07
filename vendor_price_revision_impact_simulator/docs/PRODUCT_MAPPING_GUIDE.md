# Exact product identity review (PR-07)

This phase resolves supplier rows to existing `product.product` variants. It never
creates or edits product master data or vendor prices. Product identity verification
is separate from commercial price approval. PR-06 structural readiness remains a
mandatory gate; PR-08 commercial normalization has not started.

## Operator workflow

1. A Configuration Administrator creates an explicit company identity policy under
   Configuration / Exact Product Identity Policy. Choose whether internal codes,
   explicit barcode input, unique template variants and services are eligible.
   Barcode matching defaults to disabled. Policy changes require a reason and
   append an actor/time/version audit. No default policy is silently assumed.
2. A Purchase User validates an accessible own draft batch using PR-06, then runs
   **Run Exact Product Matching**. Purchase Managers may manage company drafts.
3. **Review Product Identity** opens paginated rows with searchable current statuses.
   Inspect the exact variant, evidence, competing candidates and reason. Product
   names/descriptions never cause an automatic match.
4. For an unresolved row, **Propose Exact Variant** selects an existing readable,
   eligible variant with a reason and finite identity period. Do not create products
   from this dialog. A proposal alone cannot produce a matched result.
5. A different Purchase Manager reviews the registry entry and independently verifies
   it with a reason. Managers cannot verify their own proposals. Contradictory exact
   evidence, overlapping verified periods, changed source identity or an ineligible
   product blocks verification. Re-run matching after verification.
6. To correct a verified mapping, explicitly retire its version, propose a new
   version and obtain independent verification. Old rows, mappings and audit evidence
   remain. Never overwrite an existing verified identity.

## Exact matching contract

The key trims surrounding whitespace only. It preserves case, punctuation, Unicode
and leading zeros. Shared/company products and shared/company supplier references
are considered only inside the batch company. Vendor partner ID is exact; parent
vendors, branches and other companies are not inferred. Supplier reference searches
read identity fields only; dates, tiers and prices do not select a commercial baseline.

A valid unchanged verified registry selection has priority. Otherwise exact vendor
references, enabled internal SKU identifiers and explicitly enabled barcodes are
considered together. Conflicting products at any level require review; the first
record ID never wins. A template reference with multiple variants is ambiguous.
A unique template variant requires the explicit company policy. Archived, inactive,
nonpurchasable and policy-disallowed service products cannot resolve. Missing or
inaccessible candidates yield an authorized-scope unmatched/review outcome without
revealing another company's products. No fuzzy or product-name matching occurs.

Reusable keys are company + exact vendor + identifier kind + normalized source key
+ nonoverlapping inclusive identity period. Supplier code is preferred, then other
explicit identifier; description-only selections use a single-row key. This identity
period is not validation of a supplier price's effective dates or commercial tiers.

## Current status and history

Rows expose pending_structure, pending_match, auto_matched, manual_matched,
needs_review, ambiguous, unmatched, ineligible, stale and excluded. The batch summary
reconciles every source row and reports distinct matched products separately from
matched rows. Different quantity rows can resolve to the same variant without
collapsing their later commercial tiers. Excluded/structurally blocked rows never
enter the product-resolved handoff.

Each immutable resolution retains actor/time, exact variant/template IDs, material
product evidence (SKU, barcode, active/purchasable/type/company, base UoM ID and
variant values), source/correction identity, PR-06 result reference, lookup digest,
registry version and bounded candidates. Original files/cells and correction overlays
are unchanged. Note-only corrections require structural revalidation but can reuse
unchanged identity evidence; capture both current structural and identity references.

Product/vendor/reference/policy/registry changes are rechecked on matching and the
handoff getter. Existing results become stale; changed manual evidence requires a
new independently verified mapping version. UI values refresh on a new request;
the handoff getter explicitly rechecks evidence even within an existing transaction.
There is no global override of standard Odoo product writes.

## Security and concurrency

Odoo 20 unified `ir.access` grants intersect mandatory company/active-user restrictions.
Read-only confidential roles cannot match, propose or verify without independent
preparer/manager rights. Configuration-only users cannot read supplier rows or
product mappings. Normal workflow uses the caller's access, without sudo. Public
ORM/context commands cannot forge results, versions, verifiers or audit evidence.
Original attachment/download guards remain. Standard export privilege is also
required; exported untrusted formula-prefix text is escaped without changing source.
Current product labels moved to another company are masked in history reads and
rejected for related-product exports; original authorized snapshots remain retained.

Matching/verification lock company then batch, with read locks on existing product
and supplier identity evidence until transaction end. Serialization conflicts are
retried in a fresh transaction by Odoo; never mark a failed operation successful.
Bulk exact searches are bounded to 5,000 records per evidence type and a 40-candidate
preview. Overflow produces review-required outcomes. Batch status searches outside
one batch are capped at 20,000 authorized rows. Newly inserted master references
are detected on the next fresh-transaction check; no predicate lock freezes all product
master activity across the system.

## PR-08 handoff

Call `batch.get_product_resolved_rows()` immediately before consuming rows, in the
same transaction. Consume only its returned current rows and actual
`resolved_product_id` variants. Retain batch/company/exact vendor, original attachment
and SHA256, raw source positions, corrections, `current_result_id`, current validation
run and `product_resolution_id`, verified mapping ID/actor/time where applicable.
Never rely on a historical status or a cached Many2one alone. Keep stale, ambiguous,
unmatched, ineligible and excluded rows as explicit unresolved data, never zero exposure.

PR-08 must independently inspect the product's current base UoM and supported
packagings, effective source UoM text, currency text, MOQ/quantity text and date
provenance; validate conversions, currency/quantity/date applicability and commercial
supplier rules. PR-07 supplies identity and base UoM context only. It does not convert
UoMs/FX, choose a price baseline, validate MOQ tiers, calculate financial exposure,
approve a price or change SO/PO/stock/accounting records. Future regression must
retain variant ambiguity, maker-checker, company scope, stale evidence, source
immutability, idempotency and protected attachments.
