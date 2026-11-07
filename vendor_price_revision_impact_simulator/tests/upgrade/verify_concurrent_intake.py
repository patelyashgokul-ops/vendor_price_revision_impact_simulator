"""Only run through Odoo shell on the dedicated disposable PR05 database.

Fixtures are intentionally committed here to allow independent test sessions.
Business intake methods themselves never commit. This is not an addon action.
"""
import threading
import time

from psycopg2.errors import SerializationFailure

from odoo import Command, api
from odoo.exceptions import UserError
from odoo.tools.binary import BinaryBytes

module = 'vendor_price_revision_impact_simulator'
assert env.cr.dbname.startswith('codex_vpr_pr05_'), 'Dedicated fixture database required'
company = env.company
user = env['res.users'].with_context(no_reset_password=True).create({
    'name': 'PR05 Concurrent Preparer', 'login': 'pr05.concurrent@example.invalid',
    'company_id': company.id, 'company_ids': [Command.set(company.ids)],
    'group_ids': [Command.set(env.ref(f'{module}.group_vendor_price_revision_user').ids)],
})
vendor = env['res.partner'].create({'name': 'PR05 Concurrent Fixture Vendor'})
registry = env.registry
uid, company_id = user.id, company.id
raw = 'Code,Description\n000123,café\n'.encode('cp1252')
batch_ids = []
for number in range(2):
    revision = env['vendor.price.revision'].with_user(user).create({'vendor_id': vendor.id})
    # Distinct content avoids intentionally entering duplicate review.
    content = raw.replace(b'000123', str(number + 123).encode().rjust(6, b'0'))
    wizard = env['vendor.price.revision.import.wizard'].with_user(user).create({
        'company_id': company_id, 'revision_id': revision.id, 'file_format': 'csv',
        'upload_filename': f'concurrent-{number}.csv', 'upload_file': BinaryBytes(content),
    })
    wizard.action_upload_extract()
    batch = wizard.result_batch_id
    assert batch.state == 'extraction_failed'
    batch.csv_encoding = 'cp1252'
    batch_ids.append(batch.id)
env.cr.commit()


def race(batch_id, second_action):
    locked = threading.Event()
    attempted = threading.Event()
    results = {}

    def extractor():
        with registry.cursor() as cr:
            session = api.Environment(cr, uid, {'allowed_company_ids': [company_id]})
            batch = session['vendor.price.revision.import.batch'].browse(batch_id)
            batch._check_intake_access()
            batch._lock()
            locked.set()
            assert attempted.wait(10)
            time.sleep(0.25)  # allow the competing UPDATE to wait on this row
            assert batch.action_extract()
            cr.commit()
            results['extractor'] = 'extracted'

    def competitor():
        assert locked.wait(10)
        try:
            with registry.cursor() as cr:
                session = api.Environment(cr, uid, {'allowed_company_ids': [company_id]})
                batch = session['vendor.price.revision.import.batch'].browse(batch_id)
                assert batch.state == 'extraction_failed'  # establish old snapshot
                attempted.set()
                getattr(batch, second_action)()
                cr.commit()
                results['competitor'] = 'completed'
        except SerializationFailure:
            results['competitor'] = 'serialization_retry'
        except Exception as exc:
            results['competitor'] = type(exc).__name__

    threads = [threading.Thread(target=extractor), threading.Thread(target=competitor)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(30)
    assert not any(thread.is_alive() for thread in threads), 'Concurrent fixture timed out'
    assert results == {'extractor': 'extracted', 'competitor': 'serialization_retry'}, results
    with registry.cursor() as cr:
        session = api.Environment(cr, uid, {'allowed_company_ids': [company_id]})
        batch = session['vendor.price.revision.import.batch'].browse(batch_id)
        assert batch.state == 'extracted' and len(batch.row_ids) == 1
        assert len(batch.attempt_ids) == 2  # original encoding failure + one success
        if second_action == 'action_extract':
            assert batch.action_extract()
            assert len(batch.row_ids) == 1 and len(batch.attempt_ids) == 2
        else:
            try:
                batch.action_cancel()
            except UserError:
                pass
            else:
                raise AssertionError('Cancellation overrode completed extraction')
        cr.rollback()


race(batch_ids[0], 'action_extract')
race(batch_ids[1], 'action_cancel')
print('PR05_CONCURRENT_EXTRACT=PASS')
print('PR05_CONCURRENT_CANCEL=PASS')
print('PR05_PROBE=PASS')
