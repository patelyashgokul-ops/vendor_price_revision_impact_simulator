"""Dedicated disposable Odoo-shell probe; commits synthetic fixtures only."""
import threading
import time

from psycopg2.errors import SerializationFailure

from odoo import Command, api
from odoo.exceptions import UserError
from odoo.tools.binary import BinaryBytes

module = 'vendor_price_revision_impact_simulator'
assert env.cr.dbname.startswith('codex_vpr_pr06_')
company = env.company
user = env['res.users'].with_context(no_reset_password=True).create({
    'name': 'PR06 Concurrent Preparer', 'login': 'pr06.concurrent.' + str(time.time_ns()) + '@example.invalid',
    'company_id': company.id, 'company_ids': [Command.set(company.ids)],
    'group_ids': [Command.set(env.ref(f'{module}.group_vendor_price_revision_user').ids)],
})
vendor = env['res.partner'].create({'name': 'PR06 Concurrent Supplier'})
registry, uid, company_id = env.registry, user.id, company.id
batch_ids = []
targets = ['vendor_product_code', 'proposed_price_raw', 'currency_raw', 'purchase_uom_raw', 'min_qty_raw', 'effective_date_raw']
for number in range(4):
    revision = env['vendor.price.revision'].with_user(user).create({'vendor_id': vendor.id})
    content = f'Code,Price,Currency,UoM,MOQ,Date\nCODE-{uid}-{number},115,INR,PCS,1,2026-11-01\n'.encode()
    wizard = env['vendor.price.revision.import.wizard'].with_user(user).create({
        'company_id': company_id, 'revision_id': revision.id,
        'upload_filename': f'concurrent-{number}.csv', 'upload_file': BinaryBytes(content),
    })
    wizard.action_upload_extract()
    batch = wizard.result_batch_id
    env['vendor.price.revision.import.mapping'].with_user(user).create([
        {'batch_id': batch.id, 'column_number': n, 'target': target}
        for n, target in enumerate(targets, 1)])
    batch_ids.append(batch.id)
env.cr.commit()


def apply_action(batch, action):
    if action == 'validate':
        batch.action_validate_structure()
    elif action == 'correct':
        batch.row_ids.action_correct('proposed_price_raw', '109', 'Concurrent correction')
    elif action == 'mapping':
        batch.mapping_ids.filtered(lambda row: row.target == 'proposed_price_raw').active = False
    elif action == 'cancel':
        batch.action_cancel()


def race(batch_id, action):
    locked, attempted = threading.Event(), threading.Event()
    outcomes = {}

    def validator():
        try:
            with registry.cursor() as cr:
                session = api.Environment(cr, uid, {'allowed_company_ids': [company_id]})
                batch = session['vendor.price.revision.import.batch'].browse(batch_id)
                batch._check_review_access()
                batch._lock()
                locked.set()
                assert attempted.wait(10)
                time.sleep(0.25)
                assert batch.action_validate_structure()
                assert batch.ready_rows == 1
                cr.commit()
                outcomes['validator'] = 'complete'
        except Exception as exc:
            outcomes['validator'] = type(exc).__name__

    def competitor():
        assert locked.wait(10)
        try:
            with registry.cursor() as cr:
                session = api.Environment(cr, uid, {'allowed_company_ids': [company_id]})
                batch = session['vendor.price.revision.import.batch'].browse(batch_id)
                assert not batch.current_run_id  # establish the old snapshot
                attempted.set()
                apply_action(batch, action)
                cr.commit()
                outcomes['competitor'] = 'completed'
        except SerializationFailure:
            outcomes['competitor'] = 'serialization_retry'
        except Exception as exc:
            outcomes['competitor'] = type(exc).__name__

    threads = [threading.Thread(target=validator), threading.Thread(target=competitor)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(30)
    assert not any(thread.is_alive() for thread in threads)
    assert outcomes == {'validator': 'complete', 'competitor': 'serialization_retry'}, outcomes
    with registry.cursor() as cr:
        session = api.Environment(cr, uid, {'allowed_company_ids': [company_id]})
        batch = session['vendor.price.revision.import.batch'].browse(batch_id)
        assert batch.ready_rows == 1 and len(batch.validation_run_ids) == 1
        original = batch.current_run_id
        if action == 'cancel':
            try:
                apply_action(batch, action)
            except UserError:
                pass
            else:
                raise AssertionError('Cancellation must not discard extracted source data')
        else:
            apply_action(batch, action)
            if action == 'validate':
                assert batch.current_run_id == original and len(batch.validation_run_ids) == 1
            else:
                assert not batch.current_run_id and batch.ready_rows == 0 and batch.pending_rows == 1
                assert not original.is_current and original.result_ids.status == 'structurally_ready'
                if action == 'correct':
                    assert batch.row_ids.effective_values['proposed_price_raw'] == '109'
                    assert len(batch.correction_ids) == 1
                else:
                    batch.mapping_ids.filtered(lambda row: row.target == 'proposed_price_raw').active = True
                assert batch.action_validate_structure()
                assert batch.ready_rows == 1
        assert len(batch.row_ids) == 1
        cr.rollback()
    print('PR06_CONCURRENT_' + action.upper() + '=PASS')


for batch_id, action in zip(batch_ids, ['validate', 'mapping', 'correct', 'cancel']):
    race(batch_id, action)
print('PR06_PROBE=PASS')
