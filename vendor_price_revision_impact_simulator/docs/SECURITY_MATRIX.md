# APP 06 security contract — PR-03/PR-04 / DEV-02

Applies to Odoo Community 20.0 and the existing revision header, line, and
evidence-reference models. The installed ORM uses `res.groups.privilege`, user
`group_ids`, and unified `ir.access` permissions/restrictions. No Enterprise
security application is required.

## Current permissions

All access below also requires the record company to be in the user's authorized,
currently selected Odoo companies. Roles never assign additional companies.

| Role | Raw revision/line/evidence reads | Create and edit | Delete |
|---|---|---|---|
| Purchase User | Own revisions and their children, including retained history | Own drafts and draft children | Own draft lines only |
| Purchase Manager | Selected authorized companies | All drafts in scope; may reassign to active purchase preparers in the same company | Draft lines only |
| Finance Manager | Selected authorized companies | None | None |
| Pricing Operator | Selected authorized companies | None; no application service exists | None |
| Director | Selected authorized companies | None; no approval service exists | None |
| Auditor | Selected authorized companies | None | None |
| Sales User / Sales Manager | None | None | None |
| Configuration Administrator | None by this role alone | No commercial edits; company policy administration only | None |
| Internal employee without an APP role, portal, public | None | None | None |

Revision and source-evidence deletion are unavailable. Evidence metadata may be
corrected by authorized draft preparers, with normal ORM create/write audit
metadata retained. Changes to an owner are restricted to Purchase Managers.
Company and revision references remain immutable. No role may write a lifecycle
state or create an approved/applied revision.

## Groups and permission composition

Identifiers below belong to `vendor_price_revision_impact_simulator`.

| XML ID | Purpose |
|---|---|
| `group_vendor_price_revision_user` | Purchase User; retained PR-02 identity |
| `group_vpr_purchase_manager` | Purchase Manager |
| `group_vpr_sales_user` | Sales User |
| `group_vpr_sales_manager` | Sales Manager |
| `group_vpr_finance_manager` | Finance Manager |
| `group_vpr_pricing_operator` | Pricing Operator |
| `group_vpr_director` | Director |
| `group_vpr_auditor` | Auditor |
| `group_vpr_configuration_admin` | Configuration Administrator |
| `group_vpr_confidential_reader` | Technical read privilege implied by authorized roles |

The PR-02 XML ID `group_vendor_price_revision_user` and its memberships are
preserved as Purchase User. Its old broad grants are updated in place to own-record
read access. Separate own-draft permissions grant create/update and line deletion.
No data or existing user memberships are deleted during the upgrade.

Purchase Manager implies Purchase User and the technical
`group_vpr_confidential_reader`. Finance, Pricing Operator, Director, and Auditor
imply only the confidential reader. Sales Manager implies Sales User. Sales and
Configuration Administrator imply only `base.group_user`. No role implies system
or accounting administration. Business role names use `group_vpr_*`; the Purchase
User retains its legacy identifier to avoid duplicate roles.

Permissions compose additively. For example, Finance + Auditor remains read-only;
Sales Manager + Purchase User may prepare its own drafts; Director + Purchase
Manager may manage scoped drafts. Auditor does not subtract a separately assigned
Purchase Manager's edit authority. Role assignments and combinations must be
reviewed by an existing Odoo access-right administrator. The APP Configuration
Administrator role does not itself grant permission to edit `res.users`,
`res.groups`, `ir.access`, or companies. There is no self-service assignment API.

## Company, ownership, and method boundaries

Each model has an ungrouped `ir.access` restriction applying to CRUD. It requires
`company_id in company_ids` and an active user. In Odoo 20, `company_ids` comes from
`env.companies`; invalid or unauthorized `allowed_company_ids` raises AccessError.
Group permissions cannot widen this global intersection. Shared vendors/products
remain legitimate; company-specific relations use `_check_company_auto` and
`check_company=True`. Child company/currency fields are derived from the parent.
The retained draft-UoM constraint uses Odoo 20's reference-unit hierarchy rather
than the removed category field; it checks compatibility without doing conversion.

Header methods and all child mutation paths check actual parent write permission,
draft state, and ownership before mutation. Multi-record writes check the entire
recordset. Header One2many commands are preflighted before execution, rejecting
foreign children, relinking/clearing, and evidence removal. Child reassignment is
always rejected. Copies require read/create rights, use a fresh reference and the
current user as owner, and retain original lines/evidence on the original record.
User-supplied context flags are never authorization.

Supplier price values, vendor product identifiers, and internal notes have
server-side field groups in addition to model/record access. Existing raw models
have no Sales-only ACL. Search, count, aggregate, relational reads, and generic
exports use the same ORM restrictions; there is no elevated report endpoint.
Explicit `read()` and `export_data()` record checks also cover ID-only requests,
which need not fetch a stored field in the standard implementation. Generic export
additionally requires Odoo's independent `base.group_allow_export` privilege; APP
roles do not imply it. Export tests grant that privilege separately to prove that
APP model, field, ownership, and company restrictions still apply.

True Odoo superuser/sudo operations inherently bypass framework access rules.
Trusted technical setup/migrations can prepare draft records without ordinary
ownership checks. They still receive no approval/application workflow here;
lifecycle writes remain blocked by the business model. Limit technical account
use and audit it outside the ordinary business-role assignment process.

## Evidence, attachments, chatter, and standard Odoo exposure

PR-05 extends manual evidence references with immutable uploaded source evidence,
protected `attachment_id`, original-byte SHA256 and raw staging. Standard Odoo
content downloads require current parent/company/role authorization. Direct ID,
HTTP, token, replacement/deletion and cross-company tests use non-superusers.
No public source endpoint or token is created. See the PR-05 section below.

The revision does not inherit `mail.thread` or `mail.activity.mixin`. No followers,
activities, or automatic messages are added. PR-26/27 must enforce recipient and
follower authorization, prohibit unintended public/portal followers, keep internal
commercial notes private, and test company-safe messages/attachments before
enabling notifications.

**APP 06 restrictions do not revoke standard Odoo supplier-cost access.** The
installed product module's `access_product_supplierinfo_user` grants internal users
read permission on `product.supplierinfo`, subject to its standard company rule.
Consequently an APP Sales-only user can still read an otherwise permitted standard
supplier price while being denied APP revision data. A regression test demonstrates
this exact boundary. Core product/Purchase/Sales access is preserved; a broader
cost-confidentiality policy requires a separate reviewed scope and role audit.

## Future services must preserve these contracts

- PR-04: configuration records require their own company boundary and explicit
  Configuration Administrator grants. Configuration authority must not imply raw
  pricing, approval, application, company assignment, or global user administration.
- PR-19/20: require role + company + amount authority, independent checker identity,
  maker/self-approval controls, valid source snapshot, stale approval invalidation,
  and audited decisions. Technical administration alone is not business approval.
- PR-21/23: require an authorized Pricing Operator, valid approved snapshot,
  applicable date/vendor/product/UoM/tier, no unresolved conflicts, freshness,
  idempotency, and a complete application audit. This group grants no APP shortcut
  to write standard supplier prices.
- PR-24/25: filter every detail and aggregate by authorized records/companies;
  protect cost fields, generic exports, PDF/Excel/CSV/API outputs, and attachment
  links without unrestricted elevation. No future report models exist yet.

## Verification

`tests/test_security_roles.py` covers role matrices and combinations, ownership,
direct and embedded operations, active/allowed company contexts, aggregate/export
boundaries, role revocation, public/Sales confidentiality, standard supplier-price
visibility, and representative unchanged supplier/product prices. PR-02 regression
tests remain in the suite. `tests/upgrade/seed_pr02.py` and `verify_pr03.py` verify
an actual installation from the retained PR-02 source followed by a PR-03 update,
including retained records, ownership, sequence, and corrected legacy grants.
The original PR-02 source is retained as `evidence/pr02-source-baseline.zip`, with
its SHA-256 alongside it, so the tested pre-upgrade implementation is identifiable.
Actual execution results and limitations are recorded in `TEST_REPORT.json` and
the PR-03 evidence files; this document is not itself test evidence.


## PR-04 configuration permissions

The previously reserved Configuration Administrator role now grants create/read/
write on company-owned policy versions, margin definitions, risk thresholds and
approval definitions. Publication requires that role and an active selected
authorized company. No new revision or global user/group permissions are implied.
Purchase Managers, Finance Managers, Directors and Auditors receive read-only
configuration/audit access within selected authorized companies. Purchase Users,
Sales-only users and Pricing Operators have no access to the combined financial
policy model; narrower workflow projections remain deferred.

All five concrete configuration models have mandatory global company and active-
user restrictions. Published parent/child versions and audit entries are immutable.
Draft policy records are retained; deletion and child relinking are denied.
Audits are appended internally after authorization and cannot be forged through
public ORM methods or context flags. ID-only reads, exports and grouped searches
retain company/model boundaries. Required approval role references grant no
permissions and do not make configuration administrators business approvers.
See [configuration guide](CONFIGURATION_GUIDE.md) for the complete contract.


## PR-05 source intake and staging

Purchase Users upload for their own draft revisions. Purchase Managers intake
authorized company drafts. Batch/row/attempt reads follow revision own-record or
confidential-reader scope, intersected with mandatory company/active-user rules.
Sales-only, portal/public, unrelated employees and Configuration-only users have
no raw source access. Finance/Director/Pricing Operator/Auditor roles read only
unless independently granted draft-preparer rights. Configuration Administrators
manage resource limits without acquiring raw supplier access.

Raw rows, source evidence and attachments are immutable. Controlled same-user
private methods create batches, attempts, provenance and attachments; public ORM
creates cannot forge them. Metadata-only elevation identifies protected attachment
IDs, while content serving checks the requesting user's access. Public flags,
tokens, copies to another scope, reassignment and deletion are blocked. Standard
Odoo export privilege is independently required. Full contract:
[Import architecture](IMPORT_ARCHITECTURE.md).


## PR-06 structural review

Mappings, validation runs/results/issues, corrections and review-input events
inherit batch company and own-record/confidential-reader scope. Purchase preparers
mutate only accessible extracted batches on editable drafts; managers retain
company draft scope. Finance/Director/Pricing/Auditor readers have no automatic
correction or validation authority. Configuration-only/Sales-only/portal/public
users receive no confidential review access. Original attachment guards remain.

Mapping reparenting/deletion and nested foreign edits are denied. Validation
results/counters cannot be forged by public ORM/context defaults. Corrections,
exclusions and input changes retain append-only evidence, actual actor/time and
version. Historical issues stay traceable and never count as current after input
changes. Normal review operations do not use sudo. Generic authorized review
exports additionally escape formula-prefix text without modifying stored evidence.
See [Structural review guide](IMPORT_VALIDATION_GUIDE.md).


## PR-07 product identity

Purchase Users propose for accessible own drafts; Purchase Managers match company
drafts and independently verify another actor's proposals. Verified reusable keys
are readable by preparers in the same company; row-only proposals retain own scope.
Confidential readers retain company read access without mutation rights. Configuration
Administrators manage identity policy without gaining supplier source access. Global
company/active-user restrictions cover policy, registry, audit, resolutions and wizard.
Public create/write/copy/delete cannot forge or erase evidence. Company filtering
applies even with multiple selected companies. Related current product labels moved
elsewhere are masked/rejected in protected reads/exports; historical authorized
snapshots remain. See [Product mapping guide](PRODUCT_MAPPING_GUIDE.md).


## PR-08 commercial validation

Commercial contexts/results/issues inherit own-draft Purchase User and company
Purchase Manager/read-only confidential-reader scope, intersected with mandatory
company/active-user restrictions. Independent Purchase Managers verify ordinary
interpretations; Finance Managers verify hypothetical FX under an enabled published
PR04 policy. No self-verification, unrestricted assumptions, state forgery or price
application authority follows. Public result/context/issue mutation is denied.
Wizards validate company/batch/context links and own alias edits server-side.

Purchase Users and confidential readers gain read access to published PR04 policy
and definitions only, allowing correct current-status retrieval. Draft read/write
authority is not broadened. Ordinary supplier/FX retrieval is never elevated.
Baseline searches are exact vendor/company/variant scoped, even with multiple
selected companies and role unions. Stored baseline IDs are integers plus immutable
evidence, avoiding live supplier-price related-field traversal. Moved-product labels
and nested exports are guarded; standard export privilege and source/download guards
remain. Standard Odoo supplierinfo visibility outside APP06 is not globally changed.
See [Commercial validation guide](COMMERCIAL_PRICE_VALIDATION.md).
