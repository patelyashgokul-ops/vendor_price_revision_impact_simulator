"""Deferred, read-only database check at the actual atomic commit boundary.

Odoo precommit callbacks also run on flushing savepoint exit. A deferred
constraint instead protects the interval after the method returns: later code
cannot commit a successful receipt for a changed target or expired authority.
"""
from odoo import models


class CommitVerifiedLine(models.Model):
    _inherit = 'vendor.price.revision.application.execution.line'

    def _auto_init(self):
        result = super()._auto_init()
        self.env.cr.execute('''
        CREATE OR REPLACE FUNCTION app06_pr22_verify_committed_price() RETURNS trigger
        LANGUAGE plpgsql AS $body$
        DECLARE actual jsonb; expected jsonb; k text; actual_number numeric; expiry timestamp;
                invalidated timestamp; request_state varchar;
        BEGIN
            SELECT to_jsonb(s) INTO actual FROM product_supplierinfo s WHERE s.id=NEW.target_id;
            expected := NEW.observed_after_values;
            IF actual IS NULL THEN
                RAISE EXCEPTION 'PR22_COMMIT_TARGET_MISSING' USING ERRCODE='23514';
            END IF;
            FOREACH k IN ARRAY ARRAY['partner_id','product_tmpl_id','product_id','company_id',
                                     'currency_id','uom_id','min_qty','price','discount','delay','sequence'] LOOP
                -- Native ORM reads nullable numeric columns as zero. Existing
                -- supplier rules can legitimately retain SQL NULL discount;
                -- compare their ORM material value without rewriting metadata.
                -- Relational identity remains strict, without zero coercion.
                actual_number := (actual->>k)::numeric;
                IF k=ANY(ARRAY['min_qty','price','discount','delay','sequence']) THEN
                    actual_number := COALESCE(actual_number,0);
                END IF;
                IF actual_number IS DISTINCT FROM (expected->>k)::numeric THEN
                    RAISE EXCEPTION 'PR22_COMMIT_TARGET_CHANGED' USING ERRCODE='23514';
                END IF;
            END LOOP;
            FOREACH k IN ARRAY ARRAY['date_start','date_end','product_code','product_name'] LOOP
                IF NULLIF(actual->>k,'') IS DISTINCT FROM NULLIF(NULLIF(expected->>k,'false'),'') THEN
                    RAISE EXCEPTION 'PR22_COMMIT_TARGET_CHANGED' USING ERRCODE='23514';
                END IF;
            END LOOP;
            SELECT r.approval_valid_until, r.approval_invalidated_at, r.state
              INTO expiry, invalidated, request_state
              FROM vendor_price_revision_application_execution e
              JOIN vendor_price_revision_approval_request r ON r.id=e.request_id
             WHERE e.id=NEW.execution_id;
            IF request_state IS DISTINCT FROM 'approved' OR invalidated IS NOT NULL OR
                (expiry IS NOT NULL AND (clock_timestamp() AT TIME ZONE 'UTC')>=expiry) THEN
                RAISE EXCEPTION 'PR22_COMMIT_AUTHORITY_EXPIRED_OR_INVALIDATED' USING ERRCODE='23514';
            END IF;
            RETURN NEW;
        END; $body$;
        DROP TRIGGER IF EXISTS app06_pr22_price_receipt_guard
            ON vendor_price_revision_application_execution_line;
        CREATE CONSTRAINT TRIGGER app06_pr22_price_receipt_guard
            AFTER INSERT ON vendor_price_revision_application_execution_line
            DEFERRABLE INITIALLY DEFERRED FOR EACH ROW
            EXECUTE FUNCTION app06_pr22_verify_committed_price();
        ''')
        return result
