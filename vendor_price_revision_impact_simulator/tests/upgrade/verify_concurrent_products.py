"""Two independent real database sessions; dedicated disposable synthetic data only."""
import threading
import time
from psycopg2.errors import SerializationFailure
from odoo import Command, api
from odoo.exceptions import ValidationError, UserError
from odoo.tools.binary import BinaryBytes
from odoo.addons.vendor_price_revision_impact_simulator.models.product_resolution import company_lock

assert env.cr.dbname.startswith('codex_vpr_pr07_')
module = 'vendor_price_revision_impact_simulator'
company = env['res.company'].with_context(install_demo=True).create({'name': 'PR07 Concurrency ' + str(time.time_ns())})
users = env['res.users'].with_context(no_reset_password=True).create([
    {'name': 'PR07 Concurrent ' + role, 'login': role + str(time.time_ns()) + '@example.invalid',
     'company_id': company.id, 'company_ids': [Command.set(company.ids)],
     'group_ids': [Command.set(env.ref(module + '.' + group).ids)]}
    for role, group in [('preparer', 'group_vendor_price_revision_user'), ('manager1', 'group_vpr_purchase_manager'), ('manager2', 'group_vpr_purchase_manager')]])
ctx = {'allowed_company_ids': company.ids}
preparer, manager1, manager2 = users
vendor = env['res.partner'].create({'name': 'PR07 Concurrent Supplier'})
policy = env['vendor.price.revision.product.policy'].with_company(company).create({'company_id': company.id, 'change_reason': 'Concurrency fixture'})
product = env['product.product'].create({'name': 'PR07 Concurrent Product', 'default_code': 'RACE-EXACT-' + str(company.id), 'company_id': company.id})
batches = []
for n in range(5):
    revision = env['vendor.price.revision'].with_user(preparer).with_context(**ctx).create({'vendor_id': vendor.id, 'company_id': company.id})
    code = product.default_code if n != 3 else 'REGISTRY-RACE'
    source = f'Code,Price,Currency,UoM,MOQ,Date,Probe\n{code},115,INR,PCS,1,2026-11-01,{n}\n'.encode()
    wizard = env['vendor.price.revision.import.wizard'].with_user(preparer).with_context(**ctx).create({'company_id': company.id, 'revision_id': revision.id, 'upload_file': BinaryBytes(source), 'upload_filename': f'race-{n}.csv'})
    wizard.action_upload_extract()
    batch = wizard.result_batch_id
    env['vendor.price.revision.import.mapping'].with_user(preparer).with_context(**ctx).create([
        {'batch_id': batch.id, 'column_number': i, 'target': target} for i,target in enumerate(['vendor_product_code','proposed_price_raw','currency_raw','purchase_uom_raw','min_qty_raw','effective_date_raw'],1)])
    batch.action_validate_structure()
    batches.append(batch.id)
registry_batch = env['vendor.price.revision.import.batch'].with_user(preparer).with_context(**ctx).browse(batches[3])
proposals = [registry_batch.row_ids.action_propose_product(product.id, 'Independent supplier identity', '2026-01-01','2026-12-31') for _ in range(2)]
proposal_ids = [p.id for p in proposals]
registry = env.registry
uid, mid1, mid2, company_id, product_id = preparer.id, manager1.id, manager2.id, company.id, product.id
env.cr.commit()

def race(label, first, second, expected_second):
    held, attempted, release = threading.Event(), threading.Event(), threading.Event()
    outcomes = {}
    def a():
        try:
            with registry.cursor() as cr:
                session = api.Environment(cr, uid, ctx)
                first(session)
                held.set()
                assert attempted.wait(10)
                time.sleep(.3)
                assert not release.is_set(), 'Competing mutation bypassed held lock'
                cr.commit()
                outcomes['first'] = 'committed'
        except Exception as exc:
            outcomes['first'] = type(exc).__name__ + ':' + str(exc)
            held.set()
    def b():
        assert held.wait(10)
        try:
            with registry.cursor() as cr:
                session = api.Environment(cr, uid, ctx)
                # Establish a repeatable-read snapshot before competing actions.
                session['vendor.price.revision.import.batch'].browse(batches[0]).read(['state'])
                attempted.set()
                second(session)
                cr.commit()
                outcomes['second'] = 'committed'
        except SerializationFailure:
            outcomes['second'] = 'serialization_retry'
        except Exception as exc:
            outcomes['second'] = type(exc).__name__ + ':' + str(exc)
        finally:
            release.set()
    threads=[threading.Thread(target=a), threading.Thread(target=b)]
    for t in threads: t.start()
    for t in threads: t.join(35)
    assert not any(t.is_alive() for t in threads), label
    assert outcomes == {'first':'committed','second':expected_second}, (label,outcomes)
    print('PR07_CONCURRENT_' + label + '=PASS ' + str(outcomes))

def batch(session,n): return session['vendor.price.revision.import.batch'].browse(batches[n])
race('MATCH', lambda s: batch(s,0).action_match_products(), lambda s: batch(s,0).action_match_products(), 'serialization_retry')
with registry.cursor() as cr:
    s=api.Environment(cr,uid,ctx); b=batch(s,0)
    assert b.action_match_products() and len(b.product_resolution_ids)==1 and len(b.get_product_resolved_rows())==1
    cr.commit()
race('CORRECT',lambda s:batch(s,1).action_match_products(),lambda s:batch(s,1).row_ids.action_correct('vendor_product_code','CHANGED','Concurrent identity correction'),'serialization_retry')
with registry.cursor() as cr:
    s=api.Environment(cr,uid,ctx);b=batch(s,1);original=b.product_resolution_ids
    b.row_ids.action_correct('vendor_product_code','CHANGED','Fresh correction retry')
    try: b.get_product_resolved_rows()
    except UserError: pass
    else: raise AssertionError('Structurally stale rows entered handoff')
    assert b.row_ids.product_match_status=='stale'
    b.action_validate_structure();assert b.row_ids.product_match_status=='stale' and original.exists()
    cr.commit()
def verify(s,index,manager):
    return s['vendor.price.revision.product.mapping'].browse(proposal_ids[index]).with_user(manager).action_confirm_mapping('Independent concurrent check')
race('VERIFY',lambda s:verify(s,0,mid1),lambda s:verify(s,1,mid2),'serialization_retry')
with registry.cursor() as cr:
    s=api.Environment(cr,uid,ctx)
    try:
        with cr.savepoint(): verify(s,1,mid2)
    except ValidationError: pass
    else: raise AssertionError('Overlapping verification silently succeeded')
    b=batch(s,3);b.action_match_products();assert b.row_ids.product_match_status=='manual_matched'
    cr.commit()
race('RETIRE',lambda s:batch(s,3).action_match_products(),lambda s:s['vendor.price.revision.product.mapping'].browse(proposal_ids[0]).with_user(mid1).action_retire_mapping('Concurrent retirement'),'serialization_retry')
with registry.cursor() as cr:
    s=api.Environment(cr,uid,ctx)
    s['vendor.price.revision.product.mapping'].browse(proposal_ids[0]).with_user(mid1).action_retire_mapping('Fresh retirement retry')
    assert not batch(s,3).get_product_resolved_rows()
    cr.commit()
# Matching holds read locks on master evidence through commit; archival waits.
race('ARCHIVE',lambda s:batch(s,4).action_match_products(),lambda s:s['product.product'].browse(product_id).sudo().write({'active':False}),'committed')
with registry.cursor() as cr:
    s=api.Environment(cr,uid,ctx);b=batch(s,4)
    assert b.row_ids.product_match_status=='stale' and not b.get_product_resolved_rows()
    assert b.product_resolution_ids.product_snapshot['active'] is True
    cr.rollback()
print('PR07_PROBE=PASS')
