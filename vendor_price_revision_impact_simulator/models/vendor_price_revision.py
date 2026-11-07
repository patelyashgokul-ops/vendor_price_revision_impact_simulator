from odoo import Command, _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

MODULE = "vendor_price_revision_impact_simulator"
PURCHASE_USER = f"{MODULE}.group_vendor_price_revision_user"
PURCHASE_MANAGER = f"{MODULE}.group_vpr_purchase_manager"
CONFIDENTIAL_GROUPS = f"{PURCHASE_USER},{MODULE}.group_vpr_confidential_reader"

REVISION_STATES = [
    ("draft", "Draft"),
    ("validated", "Validated"),
    ("submitted", "Submitted"),
    ("under_review", "Under Review"),
    ("approved", "Approved"),
    ("rejected", "Rejected"),
    ("partially_applied", "Partially Applied"),
    ("applied", "Applied"),
    ("cancelled", "Cancelled"),
    ("superseded", "Superseded"),
]


class VendorPriceRevision(models.Model):
    _name = "vendor.price.revision"
    _description = "Vendor Price Revision"
    _order = "received_date desc, id desc"
    _check_company_auto = True

    _name_unique = models.Constraint(
        "UNIQUE(name)", "The revision reference must be unique."
    )

    name = fields.Char(
        string="Revision Reference", required=True, readonly=True, copy=False,
        index=True, default="/",
    )
    company_id = fields.Many2one(
        "res.company", required=True, readonly=True, index=True,
        default=lambda self: self.env.company,
    )
    vendor_id = fields.Many2one(
        "res.partner", string="Vendor", required=True, index=True,
        check_company=True,
    )
    currency_id = fields.Many2one(
        "res.currency", required=True, default=lambda self: self.env.company.currency_id,
        string="Proposed Price Currency",
    )
    received_date = fields.Date(default=fields.Date.context_today, required=True)
    proposed_effective_date = fields.Date(string="Proposed Effective Date")
    state = fields.Selection(REVISION_STATES, default="draft", required=True, readonly=True, index=True)
    owner_id = fields.Many2one(
        "res.users", string="Revision Owner", required=True,
        default=lambda self: self.env.user, check_company=True,
    )
    line_ids = fields.One2many("vendor.price.revision.line", "revision_id", string="Price Lines")
    evidence_ids = fields.One2many(
        "vendor.price.revision.evidence", "revision_id", string="Source Evidence"
    )
    line_count = fields.Integer(compute="_compute_line_count", string="Lines")
    notes = fields.Text(string="Internal Notes", groups=CONFIDENTIAL_GROUPS)

    def read(self, fields=None, load="_classic_read"):
        # ID-only requests must enforce the same boundary as stored-field reads.
        self.check_access("read")
        return super().read(fields=fields, load=load)

    def export_data(self, fields_to_export):
        self.check_access("read")
        return super().export_data(fields_to_export)

    def _check_draft_edit_access(self):
        """Check the complete recordset before any parent or child mutation."""
        self.check_access("write")
        if any(revision.state != "draft" for revision in self):
            raise UserError(_("Only draft revisions can be edited."))
        # Technical superuser operations remain trusted; no lifecycle gate is bypassed.
        if not self.env.su:
            if not self.env.user.active or not self.env.user.has_group(PURCHASE_USER):
                raise AccessError(_("Only purchase preparers can edit revision drafts."))
            if not self.env.user.has_group(PURCHASE_MANAGER) and any(
                revision.owner_id != self.env.user for revision in self
            ):
                raise AccessError(_("Purchase users may only edit their own drafts."))

    @api.model
    def _check_owner_assignment(self, company, owner):
        if owner and company not in owner.company_ids:
            raise ValidationError(_("The revision owner must be allowed in the revision company."))
        if not self.env.su and owner and (
            not owner.active or owner.share or not owner.has_group(PURCHASE_USER)
        ):
            raise AccessError(_("The revision owner must be an active purchase preparer."))

    def _check_child_commands(self, vals, creating=False):
        """Preflight nested commands before the ORM can execute a partial batch."""
        for field_name, model_name in (
            ("line_ids", "vendor.price.revision.line"),
            ("evidence_ids", "vendor.price.revision.evidence"),
        ):
            for command in vals.get(field_name, []):
                operation = command[0]
                if operation == Command.CREATE:
                    if {"revision_id", "company_id", "currency_id"}.intersection(command[2]):
                        raise AccessError(_("Child ownership and currency are derived from the revision."))
                    continue
                if creating or operation in (Command.LINK, Command.SET, Command.CLEAR):
                    raise AccessError(_("Existing child records cannot be relinked or cleared in bulk."))
                if field_name == "evidence_ids" and operation in (Command.DELETE, Command.UNLINK):
                    raise AccessError(_("Source evidence references must be retained."))
                child = self.env[model_name].browse(command[1])
                child.check_access("write" if operation == Command.UPDATE else "unlink")
                if child.revision_id not in self:
                    raise AccessError(_("Nested commands must target this revision's own children."))
                child.revision_id._check_draft_edit_access()

    @api.depends("line_ids")
    def _compute_line_count(self):
        counts = self.env["vendor.price.revision.line"]._read_group(
            [("revision_id", "in", self.ids)], ["revision_id"], ["__count"]
        )
        count_by_revision = {revision.id: count for revision, count in counts}
        for revision in self:
            revision.line_count = count_by_revision.get(revision.id, 0)

    @api.model_create_multi
    def create(self, vals_list):
        self.check_access("create")
        if not self.env.su and (
            not self.env.user.active or not self.env.user.has_group(PURCHASE_USER)
        ):
            raise AccessError(_("Only purchase preparers can create revision drafts."))
        prepared = []
        allowed_companies = self.env.companies
        for values in vals_list:
            vals = dict(values)
            self._check_child_commands(vals, creating=True)
            vals.pop("name", None)
            requested_state = vals.pop("state", "draft")
            if requested_state != "draft":
                raise AccessError(_("A revision can only be created in Draft state."))
            company = self.env["res.company"].browse(vals.get("company_id") or self.env.company.id)
            if company not in allowed_companies:
                raise AccessError(_("You cannot create revisions for this company."))
            owner_id = vals.get("owner_id", self.env.user.id)
            owner = self.env["res.users"].browse(owner_id)
            if not self.env.su and owner != self.env.user and not self.env.user.has_group(PURCHASE_MANAGER):
                raise AccessError(_("Only purchase managers may assign a different draft owner."))
            self._check_owner_assignment(company, owner)
            vals["company_id"] = company.id
            sequence_reference = self.env["ir.sequence"].next_by_code("vendor.price.revision")
            if not sequence_reference:
                raise UserError(_("The vendor revision sequence is not configured."))
            vals["name"] = sequence_reference
            prepared.append(vals)
        return super().create(prepared)

    def write(self, vals):
        self._check_draft_edit_access()
        self._check_child_commands(vals)
        if "state" in vals:
            raise AccessError(_("Lifecycle changes are not available in this development step."))
        if "name" in vals:
            raise AccessError(_("Revision references are assigned by the system."))
        if "company_id" in vals:
            raise AccessError(_("A revision company cannot be changed after creation."))
        for revision in self:
            if revision.state != "draft":
                raise UserError(_("Only draft revisions can be edited."))
            if {"vendor_id", "currency_id"}.intersection(vals) and (revision.line_ids or revision.evidence_ids):
                raise UserError(_("Vendor and currency cannot change after lines or evidence have been added."))
        if "owner_id" in vals:
            owner = self.env["res.users"].browse(vals["owner_id"])
            if not self.env.su and not self.env.user.has_group(PURCHASE_MANAGER) and any(
                revision.owner_id != owner for revision in self
            ):
                raise AccessError(_("Only purchase managers may reassign draft ownership."))
            for revision in self:
                self._check_owner_assignment(revision.company_id, owner)
        return super().write(vals)

    def copy(self, default=None):
        self.ensure_one()
        self.check_access("read")
        if self.state != "draft":
            raise UserError(_("Only draft revisions can be duplicated."))
        defaults = dict(default or {})
        defaults.update({
            "name": "/", "state": "draft", "owner_id": self.env.user.id,
            "line_ids": [], "evidence_ids": [],
        })
        return super().copy(defaults)

    def unlink(self):
        self.check_access("unlink")
        raise UserError(_("Revision records are retained for audit; deletion is not available."))


class VendorPriceRevisionLine(models.Model):
    _name = "vendor.price.revision.line"
    _description = "Vendor Price Revision Line"
    _order = "sequence, id"
    _check_company_auto = True

    _nonnegative_proposed_price = models.Constraint(
        "CHECK(proposed_price >= 0)", "Proposed price cannot be negative."
    )
    _nonnegative_min_qty = models.Constraint(
        "CHECK(min_qty >= 0)", "Minimum quantity cannot be negative."
    )

    revision_id = fields.Many2one(
        "vendor.price.revision", required=True, ondelete="cascade", index=True
    )
    company_id = fields.Many2one(
        related="revision_id.company_id", store=True, readonly=True, index=True
    )
    sequence = fields.Integer(default=10)
    product_id = fields.Many2one("product.product", check_company=True, index=True)
    vendor_product_code = fields.Char(string="Vendor Product Code", index=True, groups=CONFIDENTIAL_GROUPS)
    vendor_product_name = fields.Char(string="Vendor Product Name", groups=CONFIDENTIAL_GROUPS)
    proposed_price = fields.Monetary(
        string="Proposed Unit Price", currency_field="currency_id", default=0.0, groups=CONFIDENTIAL_GROUPS
    )
    price_is_set = fields.Boolean(
        string="Price Provided", default=False, groups=CONFIDENTIAL_GROUPS,
        help="Distinguishes an unset draft price from a genuine zero-price proposal.",
    )
    currency_id = fields.Many2one(related="revision_id.currency_id", store=True, readonly=True)
    purchase_uom_id = fields.Many2one("uom.uom", string="Source Purchase Unit")
    min_qty = fields.Float(string="Minimum Quantity", default=0.0, digits="Product Unit of Measure")
    source_line_number = fields.Integer(string="Source Line Number")
    notes = fields.Text(string="Internal Line Notes", groups=CONFIDENTIAL_GROUPS)

    def read(self, fields=None, load="_classic_read"):
        self.check_access("read")
        return super().read(fields=fields, load=load)

    def export_data(self, fields_to_export):
        self.check_access("read")
        return super().export_data(fields_to_export)

    @api.model_create_multi
    def create(self, vals_list):
        self.check_access("create")
        prepared = []
        for values in vals_list:
            vals = dict(values)
            if "company_id" in vals:
                raise AccessError(_("Line company is derived from its revision."))
            if "currency_id" in vals:
                raise AccessError(_("Line currency is derived from its revision."))
            if vals.get("proposed_price", 0.0) < 0:
                raise ValidationError(_("Proposed price cannot be negative."))
            if vals.get("min_qty", 0.0) < 0:
                raise ValidationError(_("Minimum quantity cannot be negative."))
            revision = self.env["vendor.price.revision"].browse(vals.get("revision_id"))
            if not revision or revision.state != "draft":
                raise UserError(_("Lines can only be added to a draft revision."))
            revision._check_draft_edit_access()
            if "proposed_price" in vals and (
                "price_is_set" not in vals or vals["proposed_price"] > 0
            ):
                vals["price_is_set"] = True
            if not vals.get("price_is_set"):
                vals["proposed_price"] = 0.0
            prepared.append(vals)
        return super().create(prepared)

    def write(self, vals):
        self.check_access("write")
        self.revision_id._check_draft_edit_access()
        if "revision_id" in vals:
            raise AccessError(_("A revision line cannot be reassigned after creation."))
        if "company_id" in vals or "currency_id" in vals:
            raise AccessError(_("Line company and currency are derived from the revision."))
        for line in self:
            if line.revision_id.state != "draft":
                raise UserError(_("Lines can only be edited on a draft revision."))
        values = dict(vals)
        if values.get("proposed_price", 0.0) < 0:
            raise ValidationError(_("Proposed price cannot be negative."))
        if values.get("min_qty", 0.0) < 0:
            raise ValidationError(_("Minimum quantity cannot be negative."))
        if "proposed_price" in values and (
            "price_is_set" not in values or values["proposed_price"] > 0
        ):
            values["price_is_set"] = True
        if values.get("price_is_set") is False:
            values["proposed_price"] = 0.0
        return super().write(values)

    def unlink(self):
        self.check_access("unlink")
        self.revision_id._check_draft_edit_access()
        if any(line.revision_id.state != "draft" for line in self):
            raise UserError(_("Lines can only be deleted from a draft revision."))
        return super().unlink()

    @api.constrains("product_id", "purchase_uom_id")
    def _check_product_uom_reference(self):
        for line in self:
            if line.product_id and line.purchase_uom_id:
                # Odoo 20 replaced UoM categories with reference-unit hierarchies.
                product_root = line.product_id.uom_id.parent_path.split("/")[0]
                source_root = line.purchase_uom_id.parent_path.split("/")[0]
                if product_root != source_root:
                    raise ValidationError(_("The source purchase unit must share the product's reference unit."))

    @api.constrains("source_line_number")
    def _check_source_line_number(self):
        for line in self:
            if line.source_line_number < 0:
                raise ValidationError(_("Source line number cannot be negative."))


class VendorPriceRevisionEvidence(models.Model):
    _name = "vendor.price.revision.evidence"
    _description = "Vendor Price Revision Evidence Reference"
    _order = "id"
    _check_company_auto = True

    revision_id = fields.Many2one(
        "vendor.price.revision", required=True, ondelete="cascade", index=True
    )
    company_id = fields.Many2one(
        related="revision_id.company_id", store=True, readonly=True, index=True
    )
    evidence_type = fields.Selection(
        [
            ("supplier_price_file", "Supplier Price File"),
            ("supplier_email", "Supplier Email"),
            ("supplier_agreement", "Supplier Agreement"),
            ("internal_review", "Internal Review"),
            ("other", "Other Commercial Evidence"),
        ], required=True, default="other",
    )
    name = fields.Char(required=True)
    source_reference = fields.Char(string="Source Reference", groups=CONFIDENTIAL_GROUPS)
    filename = fields.Char(groups=CONFIDENTIAL_GROUPS, help="Descriptive metadata for manual evidence; immutable original filename for intake evidence.")
    checksum = fields.Char(groups=CONFIDENTIAL_GROUPS, help="Legacy unverified metadata. Authenticated uploaded sources use the separate SHA-256 digest.")
    notes = fields.Text(string="Internal Notes", groups=CONFIDENTIAL_GROUPS)

    def read(self, fields=None, load="_classic_read"):
        self.check_access("read")
        return super().read(fields=fields, load=load)

    def export_data(self, fields_to_export):
        self.check_access("read")
        return super().export_data(fields_to_export)

    @api.model_create_multi
    def create(self, vals_list):
        self.check_access("create")
        for vals in vals_list:
            if "company_id" in vals:
                raise AccessError(_("Evidence company is derived from its revision."))
            revision = self.env["vendor.price.revision"].browse(vals.get("revision_id"))
            if not revision or revision.state != "draft":
                raise UserError(_("Evidence references can only be added to a draft revision."))
            revision._check_draft_edit_access()
        return super().create(vals_list)

    def write(self, vals):
        self.check_access("write")
        self.revision_id._check_draft_edit_access()
        if "revision_id" in vals:
            raise AccessError(_("An evidence reference cannot be reassigned after creation."))
        if "company_id" in vals:
            raise AccessError(_("Evidence company is derived from the revision."))
        for evidence in self:
            if evidence.revision_id.state != "draft":
                raise UserError(_("Evidence references can only be edited on a draft revision."))
        return super().write(vals)

    def unlink(self):
        self.check_access("unlink")
        raise UserError(_("Evidence references are retained for audit; deletion is not available."))
