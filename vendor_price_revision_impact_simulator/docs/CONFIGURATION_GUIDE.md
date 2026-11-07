# Company business policies — PR-04

Open **Vendor Price Simulator → Configuration → Business Settings**. A
Configuration Administrator creates an explicitly company-owned draft, supplies
a unique version, change reason and inclusive start/end dates, then defines its
margin, risk and approval rows. No configuration is created automatically on
installation or company creation. Missing setup blocks policy retrieval; it never
inherits another company's values. Monetary examples in tests are illustrative.

## Publication and history

**Publish Configuration** validates structure and records the publishing user and
time. It authorizes the configuration definition, not a supplier revision or
commercial decision. Complete risk and finance-exposure approval scales and a
company margin default are required. Each other configured approval category must
also cover the full nonnegative amount scale. Incomplete drafts remain editable.
The readiness text describes configuration structure only; simulation, approval
execution and price application remain unavailable.

Published versions, including their children, dates and active flag, cannot be
edited or deleted. Plan finite inclusive periods and publish the successor from
the following day. Future periods are supported. Overlap is rejected at
publication, including touching inclusive endpoints. Gaps are allowed between
versions but lookup on a gap fails explicitly. Backdated publication requires
both configuration authority and Odoo access-rights administration; ordinary
configuration administrators cannot retrospectively publish.

Duplicate a version to prepare a new draft. The copy retains its company and
definitions, receives a draft version label and no publication metadata. Supply
a unique version, new dates and reason before publishing. Cross-company copying
and reparenting definitions are forbidden. Published records provide stable IDs,
company, captured currency, version, effective dates, reason and publication
identity for future snapshots. A material policy change must cause approval
eligibility revalidation in PR-19/20; it must never recalculate old snapshots.

Every create/edit/publication appends an audit with actor, timestamp, model/row,
operation and before/after stored values (JSON; relational references use IDs).
Drafts and audit records are retained too. Only a private, narrowly elevated
append operation writes audits after policy authorization; user retrieval and
policy mutation do not use sudo. Context flags cannot enable publication or
audit changes. Technical superusers retain their inherent framework privileges.

Company-row mutations serialize policy edits and publication. A no-op row update
forces a serialization retry under Odoo's repeatable-read isolation, so competing
transactions cannot both validate against an obsolete company-policy snapshot.

## Financial definitions

Cost basis choices distinguish current, proposed and evidenced negotiated vendor
prices from existing accounting stock cost, replacement estimates and estimated
landed cost. Existing stock uses company accounting context; replacement cost
requires an explicit procurement estimate. Additional costs are excluded unless
evidenced nonrecoverable charges are selected. Confirmed purchase commitments
retain agreed prices. These settings define inputs; no costs are calculated.

Amounts in risk and approval definitions are in the version's captured company
currency. Currency mismatch is rejected; no conversion is performed. Rate policy
uses simulation effective date, a required company reference date, or an explicit
finance-governed scenario rate. FX override governance stores authorization
requirements, not actual rates or an override endpoint. Missing FX blocks the
affected calculation. Odoo currency precision governs amount comparisons and
rounding. Changing company currency requires a new validated policy; the old
version's currency remains traceable.

UoM policies require comparable purchase units or verified reference-unit
conversion. Unknown or incompatible units block comparison. Tier quantities use
normalized purchase units. No normalization or tier selection is performed.
Gross margin assumes net revenue and excludes recoverable tax; tax-inclusive
prices need explicit Odoo tax context. Unknown tax/cost treatment is incomplete,
never zero. No custom tax engine or accounting operations are introduced.

## Margins, risk and approval definitions

Gross margin percentage fields store percentage points: **20 means 20%**. Margin
differs from markup. Explicit numeric thresholds are required and must be finite,
with `0 <= minimum <= target < 100`. Precedence within a published version is
product, exact product category, company default. Parent categories are not
implicitly inherited. Every exception requires a reason and publication of its
version; drafts are preparation only. Duplicate active scope keys are rejected.
Shared products may have separate policies in each company. Company-owned
products must match the policy company. Children inherit their parent's dates.

Risk/approval intervals use **[minimum, maximum)**. Use the explicit open-ended
flag for the final tier, with maximum left at zero. Negative/nonfinite boundaries,
reversed or overlapping ranges, and precision-equivalent reversed bounds are
rejected. A complete scale starts at zero, has no gaps, and ends open-ended.
Risk retrieval returns definitions only: missing exposure is not LOW risk and no
financial risk score is calculated. Mandatory exception contracts require finance
review for negative margin, commercial review for contract conflicts,
revalidation of stale results, and blocking incomplete decisions, missing
approval, invalid application dates and unauthorized application attempts.

Approval categories are **additive**, not alternatives. Within each configured
category, amount intervals choose one definition; all roles on that row are
required. The supported role references are Purchase Manager, Finance Manager,
Sales Manager and Director. Definitions grant no model or group permissions.
Configuration Administrator, Auditor and Pricing Operator are not approval roles.
Distinct independent approvers must cover every role and the company minimum;
same-user stage reuse and delegation are disabled. No users are assigned and no
approval decisions or stages execute in this phase.

## Governance, security and missing data

Future proposals are allowed by default. Backdated proposals remain draft
evidence subject to review; application is restricted/reviewed or blocked.
Overlap conflicts require review; stale revisions require revalidation; expired
offers require commercial review. Price applicability must respect dates and
quantity tiers. Supplier proposal dates and authorized application dates differ.
There are no switches to disable confirmed-document protection, posted-accounting
protection, historical-valuation protection, company isolation or authorization.
Future engines must retain these invariants regardless of configuration.

Unmapped products block lines, missing FX blocks calculation, invalid units block
comparison, ambiguous prices require review, missing costs mark results
incomplete, and missing authority blocks approval eligibility. Notification
preferences store future event choices only, with company-authorized recipients
and event deduplication. No emails, activities, cron jobs or templates are created.

Configuration Administrators create/edit/publish within their selected authorized
companies only. Purchase Managers, Finance Managers, Directors and Auditors have
read-only access to these financial definitions and history. Purchase Users,
Sales-only roles and Pricing Operators have no access to the combined financial
configuration model; narrower commercial/application projections are deferred
until their consuming workflows exist. Additional separately assigned roles add
their permissions, always within the mandatory company restriction. Root-menu
visibility confers no raw revision rights. Read, ID-only read, export and grouped
search follow model access. Audit history cannot be forged or deleted.

## Retrieval contract for later prompts

Use the normal user's environment and explicit authorized company and date:

```python
config = env['vendor.price.revision.config'].get_company_revision_config(company, date)
margin = config.get_applicable_margin_policy(product)
risk_definitions = config.get_applicable_risk_rules()
approval = config.get_applicable_approval_policy(category, normalized_amount, config.currency_id)
```

The first method requires exactly one published applicable version and rechecks
currency and dependent setup. The instance methods also support inspecting draft
definitions during setup; future operational consumers must obtain their version
through the dated published lookup first. Returned recordsets include provenance
through `config_id`; no fallback, financial calculations, FX conversions,
approval decisions, notifications or price writes occur. Unknown categories,
missing policy, incomplete scales and unnormalized amounts fail explicitly.
Call approval retrieval for every category required by the later business
workflow; categories are additive and not automatically selected by this phase.

PR-05 import, PR-08 normalization, PR-14/15 financial calculations, PR-19/20
approval and PR-21/23 application remain deferred. Configuration ready does not
mean those features or the application are production ready.
