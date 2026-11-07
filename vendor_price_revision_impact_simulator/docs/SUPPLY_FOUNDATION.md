# PR09 — Current inventory and incoming supply foundation

Odoo 20.0 Community. `purchase_stock` supplies the purchase/stock integration and
its Community accounting/valuation dependency. This addon does not change an
existing repository's Odoo version. PR09 collects evidence only; PR10 has not
started. No demand allocation, order exposure, replacement valuation, margin,
supplier price application or realized benefit is calculated here.

## Operator workflow

1. A Configuration Administrator grants an active internal commercial user a
   company, exact warehouses and optional confidential cost access. No grant is
   installed by default. Grants are explicit permission to use the analytical
   service described below. Review the business justification before granting.
2. Classify each exact stock location in Supply Location configuration. Saleable,
   receiving, quality, staging, transit and excluded are separate roles. A saleable
   parent does not implicitly authorize its children. Classify children explicitly.
3. Complete the existing PR06, PR07 and PR08 workflow. Only current commercially
   valid rows and their exact variants enter supply discovery.
4. Open the batch's **Collect Supply / Review Terms** wizard. Select warehouses
   and whether costs are requested. The result is a frozen current-time snapshot.
   Review per-variant/warehouse/base-UoM totals, individual buckets and issues.
5. For documented firm incoming price protection, propose the purchase line ID,
   classification and supplier evidence reason through the same wizard. Another
   Purchase Manager with cost access to that warehouse verifies it through the
   terms form. PO confirmation and locking alone are not price guarantees.
6. Collect again after verification. Use **Check Current Sources** before relying
   on historical evidence. Downstream code must use `get_current_supply()`.

## Quantities and non-overlap

One quant contributes physical and reserved stock once. Unreserved is physical
minus that quant's reservation; outbound move reservations are not subtracted
again. Eligible free is the nonnegative unreserved quantity only in an explicitly
saleable active internal location, with an active tracked stock product, valid
lot evidence when required, no scrap/inventory usage, no third-party owner and no quantity
anomaly. Raw negative quantities and overreservations remain visible with issues;
they do not become fictitious available stock. Unknown and not-applicable values
remain null rather than manufactured zero supply.

Consigned stock retains owner/quant provenance and is excluded from company-owned
eligible stock and cost. Receiving and quality stock is received pending putaway,
not supplier-unreceived. Staging, scrap and transit are separate exclusions.
Company-owned transit can be mapped explicitly; shared transit cannot be safely
attributed from a shared product and is not counted as company warehouse stock.
Installed lot expiration evidence is checked when available; this is not a FEFO
allocation engine or a substitute for the warehouse's quality disposition.

One purchase-line bucket summarizes actual supplier boundary moves, including
backorders. Done receipt quantities are separate from pending receipt requirements
and cancelled remainder. Internal receipt steps and transfers are nonadditive
references. A two-step PO100 received40 into Input yields received physical40,
eligible free0 and supplier-unreceived60, not incoming100 plus received40.
Returning received goods does not imply a replacement purchase commitment.
Unreconciled boundaries, duplicate receipt requirements, missing moves, manual
receipt methods, incompatible units, dropshipping or ambiguous replacement chains
remain review-required rather than being guessed or capped. Service and untracked
products do not gain invented warehouse availability.

Totals are keyed by exact variant, warehouse and product base UoM. Never sum unlike
products or units. An all-warehouse company figure means only the authorized
selected warehouses; partial scope must never be presented as company-wide stock.
Incoming candidate supply and verified firm incoming are distinct. Firm incoming
is a subset, never an additional supply bucket.

## Costs and commercial terms

Standard price and company AVCO are current accounting reference estimates,
not traced historical acquisition prices. FIFO quant/location/lot acquisition
cost is unavailable here: Odoo20 uses move valuation fields and no exact quant
layer allocation is inferred. Missing/zero accounting cost stays unavailable.
There is no `stock.valuation.layer` assumption for this target version.

Incoming evidence captures original PO price, discount, currency, UoM and taxes.
PR08 Decimal inverse-price/unit conversion and guarded company/date FX are reused.
Missing FX, future actual rates, hypothetical FX, tax-inclusive terms and
unevidenced additional charges make cost incomplete without deleting known
incoming quantity. No 1:1, earliest-rate or forecast fallback is used. Firm-price
protection requires unchanged independently verified terms, complete normalization
and the published PR04 preserve-agreed-prices policy. The attestation captures
UoM definitions and their reference hierarchy, so reinterpreting a box cannot
resurrect old firm evidence after commercial refresh. Firm describes the original
PO currency price terms; the company-currency amount is a dated FX reference,
not a hedged settlement cost. Changed terms, disputed or
pending amendments cannot remain silently protected.

## Security and trust boundary

Native Odoo warehouse, purchase and cost permissions are **not expanded** by this
addon. In this target tree, stock.quant already has an internal-user read grant;
app Purchase Users do not automatically receive native purchase-order read access.
An explicit audited analytical grant intentionally permits this addon to produce
a restricted projection despite that lack of native operational read access.
This is a privileged analytical service, not a claim that standard stock ACLs
already permit the read or that all Odoo source security is changed globally.

The private Python collector first authorizes current batch ownership/role,
selected company, every warehouse and cost mode. Only then does a fixed service
projection read bounded company/product/location/PO-warehouse domains. It cannot
accept arbitrary model names, fields or source domains from RPC. It does not
return sudo recordsets or related live source references. Scope is checked again
before publication. Grant metadata alone uses a separate narrow elevated read
for record-rule domains. Cost-free mode omits accounting and PO price projections.

Global company and all-selected-warehouse rules intersect role access. Mixed A+B
snapshots require permission for both warehouses; an intersection with just A
does not authorize the snapshot. Cost snapshots require cost grants for every
warehouse. Direct reads, searches, grouping and exports follow those same rules.
Revocation blocks retained evidence as well as new collection. Auditors remain
read-only; Sales, Portal and Configuration-only roles cannot collect commercial
supply. Generic source IDs are plain retained evidence, not elevated references.
A linked physical supplier receipt or return redirected to an unselected internal
warehouse blocks collection before evidence is published, even if its PO header
still names an approved warehouse. An authorized combined scope can retain the
inconsistency for review. Opening a source requires current analytical scope and
the user's native Odoo source read permission. Existing standard source visibility outside this app is
outside this addon boundary.

## Integrity, freshness and limits

Snapshots, buckets and issues are immutable. Refresh appends a version per batch,
warehouse selection and cost mode; identical source fingerprints reuse the last
version. Current collection time, actor, PR08 version/digest, source IDs, units,
policy, classifications and original terms are retained. A requested commercial
effective date never turns current stock into a historical inventory assertion.

Company and batch serialization plus existing-source read locks protect collection
and app review. Entire evidence publication is inside one savepoint with no
mid-transaction commits. Material quantities, reservations, receipts, cancellation,
prices, units, locations, classifications and commercial/policy changes invalidate
the consumer fingerprint. Administrative PO notes and source write timestamps
alone do not. MVCC conflicts abort rather than publishing partial success.
Existing-row locks do not freeze future inserts or create a permanent reservation;
downstream transactions must recheck current sources and handle serialization
retries. PR09 never reserves supply for future demand consumers.

Each source query has a 10,000-record hard bound and fails closed on overflow;
no truncated snapshot is treated as complete. Sources are read in bulk and move
chains are grouped in memory. This bound is not a measured load guarantee.
100/500/2,000-product and 10,000-source stress benchmarks, peak memory and manual
browser UAT must be reported as measured or NOT_MEASURED/NOT_RUN in the test report.

Known conservative review routes include ambiguous replacement-return chains,
shared transit attribution, cross-warehouse supplier receipt boundaries, tax-
inclusive purchase costs and unsupported additional charges. These cannot be
consumed as verified supply. Historical acquisition cost and location-specific
FIFO are unavailable. No blanket manual override can mark them verified.

## PR10 handoff

Call `batch.get_current_supply(warehouse_ids, costs=True)` in a fresh authorized
transaction; do not read the latest numeric snapshot ID and assume it is current.
Check per-product `quantity_verified` and nulls, review all issues, and retain the
snapshot ID/version/digest and selected warehouse scope. Quant source keys and PO
line source keys are stable identities for future unique attribution. Reservations
have already been removed from eligible free; firm incoming is a subset of incoming.
Internal transfer references do not contribute. Cost references are not replacement
cost, protected potential benefit or a realized accounting outcome. PR10 must add
its own demand, allocation, concurrency and double-counting guarantees.
