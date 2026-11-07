"""Pure comparator regression: events assumed validated; no approval/ORM fixture."""
import ast
import importlib
from pathlib import Path
import sys
import types
from types import SimpleNamespace as S
root=Path(__file__).resolve().parents[1]
package=types.ModuleType('pr23_chain_math');package.__path__=[str(root/'models')];sys.modules[package.__name__]=package
math=importlib.import_module('pr23_chain_math.monitor_math')
tree=ast.parse((root/'models/monitor_service.py').read_text(encoding='utf-8'))
method=next(m for c in tree.body if isinstance(c,ast.ClassDef) and c.name=='Observation' for m in c.body if isinstance(m,ast.FunctionDef) and m.name=='successor')
namespace=dict(compatible=math.compatible,differences=math.differences,historical=lambda line,cache:True)
exec(compile(ast.Module(body=[method],type_ignores=[]),'<actual_successor_comparator>','exec'),namespace)
base=dict(partner_id=1,product_tmpl_id=2,product_id=3,company_id=4,min_qty='100',price='109',currency_id=5,uom_id=6,
 date_start='2026-10-30',date_end=False,discount='0',delay=1,sequence=1,product_code=False,product_name=False)
def event(i,values,boundary=False):
 return S(id=i,target_id=77,execution_id=S(id=i,verified_at=i,state='VERIFIED'),observed_after_values=values,plan_line_id=S(evidence={'boundary':boundary}))
events=[event(1,base),event(2,dict(base,price='112')),event(3,dict(base,price='112',date_end='2026-10-31'),True),event(4,dict(base,price='115',date_end='2026-10-31'))]
engine=S(history={77:events},cache={})
result,invalid=namespace['successor'](engine,events[0])
assert result is events[-1] and not invalid,('Stepwise valid date closure was not followed',result.id,invalid)
print('PR23_CHAIN_COMPARATOR=PASS (pure unit; no authorization claim)')
