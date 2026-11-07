# Purchase commitment evidence — PR12

This layer records actual RFQ/PO commercial terms, not payables, inventory value,
approved amendments or final company exposure. It never changes purchasing,
supplier prices, stock, billing, payments or accounting records.

## Collection and source authority

Choose **Collect Purchase Commitments** on an extracted draft revision batch.
Select every authorized warehouse explicitly. The existing PR09 cost grant and
company restriction apply. Purchase preparers collect their own editable batches;
Purchase Managers can manage authorized draft batches. Read-only Finance/Director/
Auditor roles can inspect permitted history but do not gain preparation rights.
Sales-only, configuration and portal roles do not acquire confidential evidence.

The fixed analytical service reads only the selected company, relevant vendor
commercial identity, current PR08 exact variants and warehouse purchase sources.
It does not grant native Purchase Administrator access. Native PO drilldown requires
ordinary source permissions and current company/warehouse eligibility separately.
No unrestricted source RPC or public controller is added. Integer source IDs retain
traceability without a native related-field path into unrelated purchases.

Odoo20 states `draft`, `sent`, `to approve` are conditional. `purchase` is confirmed;
`locked` is a separate Boolean. `cancel` is excluded. Core Purchase has no supplier
quotation expiry field: validity remains unrecorded unless explicit supplier evidence
provides dates. No agreement model or supplier acknowledgement is invented.

Current `batch.get_current_supply(warehouse_ids, True)` is mandatory. Confirmed
supplier-unreceived quantities come from exact PR09 `po_line:<id>` buckets. Gross
supplier receipts, cancellations, return references, putaway movements and pending
delivery remain separately traced. PR12 never substitutes billed quantities or a
second `ordered - received` engine. Short-closed quantities stay excluded. A return
does not automatically create replacement incoming. Missing quantity stays blank.
Dropship/special-route or inconsistent boundaries remain PR09 review cases.

RFQs preserve requested quantities and recorded prices, separately labeled as
conditional. They do not add confirmed incoming or protected stock. Fully received
and short-closed confirmed lines can show a verified zero open commitment; unknown
sources cannot masquerade as zero.

## Commercial prices and comparisons

Actual `purchase.order.line.price_unit`, discount, currency and UoM are the recorded
agreement reference. Current supplierinfo prices are not substituted. Odoo20 native
purchase base-line tax computation produces a tax-excluded goods reference; Decimal
discount preparation avoids repeated subtraction and surcharge floating artifacts.
This excludes sales/purchase tax from the goods reference and does not claim a full
inventory acquisition basis including nonrecoverable tax or landed costs.

PR08 validates common-reference UoM pairs. Prices convert inversely to quantities.
Source and comparison units, factors, tax definitions and currency rounding are
frozen. Monetary report values use currency increment rounding; unit precision is
retained. Negative/unsupported bases and unallocated service/charge/discount lines
make product-attributable value incomplete. Charges are not stock and are never
arbitrarily apportioned. Full-order untaxed amounts are separate context, not open
commitment values. Current price observations do not reconstruct an original legal
price without retained history or documented evidence.

Source-currency confirmed open values and conditional RFQ values are separate
currency groups. Incomplete group totals are null; their known subtotal and missing
line count remain explicit. No cross-currency or final disputed-company total exists.

Company FX uses an explicit purchase reference date or the applicable PR04 policy's
company reference/confirmation date. Root-company rates before the requested date
take priority over shared rates; target technical rate divided by source rate sets
direction. Missing rates do not fall back to 1:1 or earliest future rates. Same
currency has an explicit identity rate. Rate IDs, dates, company and method are
captured. No res.currency.rate write occurs. Source values remain available when
company references are incomplete.

Applicable proposed prices consume current PR08 evidence for the exact variant,
effective interval and highest eligible original ordered-quantity tier. There is
no cross-order procurement aggregation. The comparison date is explicit or the
stored line arrival date. Compare net source currencies directly when equal;
otherwise use a verified common company-currency FX date for both prices. Preserve
the PR08 baseline independently: a supplier old price100 and negotiated PO95 yield
different deltas against proposal115. Proposal changes do not amend a PO.

The general proposed-price difference is conditional. A separately documented
supplier request can preserve another source-currency/source-UoM amendment price
and its conditional scenario value. Requests with an unknown included-tax basis
remain unverified. Neither general differences nor request differences are accepted
payables, realized losses or additive financial exposures. Fixed PO protection can
coexist with an unaccepted supplier amendment request.

## Supplier evidence review

From a purchase line propose a reference-only supplier assessment with reason,
classification and supporting document reference. No arbitrary attachments are
copied or published; original supplier attachments retain existing evidence ACLs.
Classifications include fixed, adjustable, amendment pending, disputed, unknown and
accepted-already-recorded. Accepted-recorded evidence must match the actual PO
source price; it cannot authorize changing that price. RFQs cannot become verified
fixed/adjustable/accepted purchase commitments by analytical classification.

A different active Purchase Manager must verify proposed evidence, with a reason,
company and cost scope and unchanged source terms. Public create/write and context
flags cannot forge outcomes. Assessments are immutable except their controlled
proposed-to-independently-verified transition. Previous assessments remain retained.
Date intervals explicitly use documented confirmation or stored delivery basis;
expired/inapplicable or source-changed assessments do not confer current protection.
Reviewer and preparer must remain authorized. Latest explicit unknown evidence
does not revive an older favorable PR09 firm assessment.

Legacy independently verified PR09 firm terms are compatible when exact source
digests remain valid. PR12 assessments do not silently mutate PR09 protection or
reallocate PR10 supply. Future consumers must inspect PR12 protection/amendment
status, underlying evidence and quantity/cost confidence together. No operational
approval or supplier amendment acceptance is performed by this workflow.

## Allocation and optional vendor billing

An optional exact PR10 allocation ID must match the current batch, supply snapshot,
cost mode and complete warehouse selection. Its current getter verifies freshness.
Incoming entries map back to the exact PR09 PO-line bucket. Allocated quantity is
counted once; open minus allocated is a scenario remainder subject to the retained
PR09/PR10 ownership and route limitations. No second stock ledger is created.
All scenarios remain separate. The linked projection requires customer-demand
scope as well as cost scope; revocation hides related quantities.

Bill detail is separately opt-in. Native read access to both account.move and
account.move.line, including every exact stored source row, is mandatory; bills are never read through sudo. Selected linked
invoice/credit lines preserve IDs, state, date, source quantity/price/currency/UoM,
and comparable net differences when supported. Cancelled/unlinked/incompatible
records cannot prove an amendment. Credit notes remain references, not PO repricing.
No bill posting or settlement exists. Billed60 and received50 from ordered100 still
have supplier-unreceived50 under PR09 semantics. Native billed quantity is labeled
in its source UoM. Missing/unrequested billing evidence is not a fabricated match. Detail-free snapshots
do not write even empty native bill relations, so they require no Accounting ACL.

Computed user bill-ID metadata is visible only to that user (or superuser),
and its cache depends on the actual acting UID. Reading another user or forging
a context UID cannot impersonate that user to enumerate bill identities.

Snapshots containing bill details require native accounting authority for direct
reads, search/group and exports. Detail-free snapshots remain separately usable.
Input wizards cannot export or traverse nested source fields as an alternate path.
Original source opening still follows native permissions.

## History, concurrency and later-stage handoff

Snapshots, lines, issues and supplier assessments retain immutable company/batch,
exact source IDs, upstream versions/digests, policy, quantities, terms, FX and review
provenance. Repeated unchanged collection reuses one current version. Earlier price
observations remain audit references, not invented legal original prices. Material
price/quantity/state/receipt/tax/policy/bill/evidence/FX/upstream changes invalidate
current getters. Unrelated notes do not. A stale prerequisite cannot publish a
current verified result. Atomic savepoints prevent interrupted success headers.

Company/batch serialization and shared locks protect existing source rows. The
business service never commits. Source edits block or require a fresh serialization
retry. Future inserts are not permanently frozen; fresh authorized transactions
and current getters are mandatory. Source reads cap10000 per query, evidence/history
also cap10000, and freshness-history filtering caps1000 snapshots. Larger workload,
peak-memory and browser results are claimed only when actually measured.

PR13/14 should call `batch.get_current_purchase_terms(warehouse_ids, include_rfqs,
allocation_id, include_bills, fx_date, comparison_date)` in a fresh transaction.
Retain exact vendor/company/variant/PO line, PR09 bucket and boundary evidence,
single PR10 allocation entry IDs, source/comparison UoM, source/company currency,
agreed/protected/proposed/request references, date/tier/FX policy and independent
value/quantity/protection/amendment/bill statuses. Unknown is not zero. Neither a
bill mismatch nor a proposal date proves an accepted PO amendment. Protected
incoming is a subset of incoming, never additional supply. Preserve company, cost,
customer-demand, native source and accounting-detail restrictions. PR12 implements
no inventory replacement attribution, final exposure, profit/margin, repricing,
approval execution or price application. Stop after PR12.
