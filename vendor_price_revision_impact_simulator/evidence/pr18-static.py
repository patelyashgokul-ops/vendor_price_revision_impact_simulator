"""Exact PR17 preservation, PR18 syntax and application safety checks."""
import ast,hashlib,json,zipfile
from pathlib import Path
from lxml import etree
r=Path(__file__).resolve().parents[1]
checks=[]
def check(label,condition):
    assert condition,label
    checks.append(label)
names=['__manifest__.py','__init__.py']+[str(p.relative_to(r)).replace('\\','/') for d in ('models','security','views','tests','data') for p in (r/d).rglob('*') if p.is_file() and p.suffix in ('.py','.xml','.csv')]
ledger={n:hashlib.sha256((r/n).read_bytes()).hexdigest() for n in sorted(names)}
sha=hashlib.sha256(json.dumps(ledger,sort_keys=True).encode()).hexdigest()
baseline=json.loads((r/'evidence/pr17-verified-source-sha256.json').read_text(encoding='utf-8'))
changed={'__manifest__.py','models/__init__.py','tests/__init__.py','models/profitability_math.py','models/reconciliation_controls.py','models/reconciliation.py','tests/test_module_foundation.py'}
with zipfile.ZipFile(r/'evidence/pr17-source-baseline.zip') as z:
    check('Exact 102-file PR17 archive',len(z.namelist())==len(baseline)==102)
    for n,h in baseline.items():
        check('Archived PR17 '+n,hashlib.sha256(z.read(n)).hexdigest()==h)
        if n not in changed:check('Unchanged prior source/test '+n,ledger[n]==h)
    old=ast.literal_eval(z.read('__manifest__.py').decode('utf-8'));new=ast.literal_eval((r/'__manifest__.py').read_text(encoding='utf-8'))
    new['data']=[v for v in new['data'] if v not in ('security/recommendation_security.xml','views/recommendation_views.xml')]
    check('Manifest only registers PR18 security/views',old==new)
    for n,line in (('models/__init__.py','from . import recommendation_math, recommendation_engine, recommendation'),('tests/__init__.py','from . import test_recommendations')):
        old=z.read(n).decode('utf-8').replace('\r\n','\n');new=(r/n).read_text(encoding='utf-8')
        check('Only PR18 registration added '+n,new.count(line)==1 and new.replace(line,'').strip()==old.strip())
    for n,fn in (('models/profitability_math.py','profitability'),('models/reconciliation_controls.py','independent_profit')):
        old=ast.parse(z.read(n).decode('utf-8'));new=ast.parse((r/n).read_text(encoding='utf-8'))
        class DefaultRevenue(ast.NodeTransformer):
            arguments=0
            assignments=0
            def visit_FunctionDef(self,node):
                if node.name==fn:
                    check('Explicit optional revenue '+fn,node.args.args[-1].arg=='baseline_revenue' and len(node.args.defaults)==1 and isinstance(node.args.defaults[0],ast.Constant) and node.args.defaults[0].value is None)
                    node.args.args.pop();node.args.defaults.pop();self.arguments+=1
                return self.generic_visit(node)
            def visit_Assign(self,node):
                if any(isinstance(v,ast.Name) and v.id=='before' for v in node.targets):
                    self.assignments+=1;return None
                return self.generic_visit(node)
            def visit_Name(self,node):
                if node.id=='before':node.id='n'
                return node
        strip=DefaultRevenue();new=strip.visit(new)
        check('Three-argument default exactly preserved '+fn,strip.arguments==strip.assignments==1 and ast.dump(old)==ast.dump(new))
    old=z.read('models/reconciliation.py').decode('utf-8').replace('\r\n','\n')
    new=(r/'models/reconciliation.py').read_text(encoding='utf-8')
    guard='for v in (record.risk_reasons or [])'
    check('Only PR16 empty-JSON adaptation',new.count(guard)==1 and new.replace(guard,'for v in record.risk_reasons')==old)
    old=z.read('tests/test_module_foundation.py').decode('utf-8').replace('\r\n','\n')
    new=(r/'tests/test_module_foundation.py').read_text(encoding='utf-8')
    added=' | self.env.ref(f"{MODULE}.menu_commercial_recommendations")'
    check('Existing foundation assertions retained exactly',new.count(added)==1 and new.replace(added,'')==old)
check('Archive checksum',hashlib.sha256((r/'evidence/pr17-source-baseline.zip').read_bytes()).hexdigest()==(r/'evidence/pr17-source-baseline.sha256').read_text(encoding='utf-8').split()[0])
# Preserve the genuine broad upgrade result while proving the exact later fix.
prior=json.loads((r/'evidence/pr18-prerounding-milestone-source-sha256.json').read_text(encoding='utf-8'))
check('Only native partial rounding and its regression changed after broad run',set(ledger)==set(prior) and {n for n,h in prior.items() if ledger[n]!=h}=={'models/recommendation_engine.py','tests/test_recommendations.py'})
with zipfile.ZipFile(r/'evidence/pr18-prerounding-source.zip') as z:
    check('Exact 108-file pre-rounding archive',len(z.namelist())==len(prior)==108)
    for n,h in prior.items():check('Archived pre-rounding source '+n,hashlib.sha256(z.read(n)).hexdigest()==h)
    old=ast.parse(z.read('models/recommendation_engine.py').decode('utf-8'));new=ast.parse((r/'models/recommendation_engine.py').read_text(encoding='utf-8'))
    def strip_customer(tree):
        methods=[v for cls in tree.body if isinstance(cls,ast.ClassDef) and cls.name=='RecommendationEngine' for v in cls.body if isinstance(v,ast.FunctionDef) and v.name=='customer_line']
        check('One exact customer pricing method',len(methods)==1);methods[0].body=[ast.Pass()]
        return next(v for v in tree.body if isinstance(v,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='VERSION' for t in v.targets))
    ov,nv=strip_customer(old),strip_customer(new)
    check('Calculation version advances for native remainder correction',ov.value.value=='pr18_exact_line_or_explicit_order_scope_native_tax_inverse_no_execution_v1' and nv.value.value=='pr18_exact_line_or_explicit_order_scope_native_tax_inverse_native_partial_remainder_v2')
    nv.value=ov.value
    check('All other application AST unchanged after broad run',ast.dump(old)==ast.dump(new))
    old=ast.parse(z.read('tests/test_recommendations.py').decode('utf-8'));new=ast.parse((r/'tests/test_recommendations.py').read_text(encoding='utf-8'))
    class StripPartialTest(ast.NodeTransformer):
        count=0
        def visit_FunctionDef(self,node):
            if node.name=='test_partial_foreign_discount_native_unchanged_rounding':self.count+=1;return None
            return self.generic_visit(node)
    strip=StripPartialTest();new=strip.visit(new)
    check('All 38 earlier recommendation tests retained unchanged',strip.count==1 and ast.dump(old)==ast.dump(new))
for n in ledger:
    if n.endswith('.py'):ast.parse((r/n).read_text(encoding='utf-8'));check('Python syntax '+n,True)
    if n.endswith('.xml'):etree.parse(str(r/n));check('XML syntax '+n,True)
for name in ('recommendation_math','recommendation_engine','recommendation'):
    tree=ast.parse((r/f'models/{name}.py').read_text(encoding='utf-8'))
    check('No native CRUD/elevation/commit '+name,not any(isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr in ('create','write','unlink','sudo','commit','action_confirm','button_confirm','action_post','_action_done','send_mail','message_post') for n in ast.walk(tree)))
engine=(r/'models/recommendation_engine.py').read_text(encoding='utf-8')
for service in ('scenario.get_current_scenario()','_prepare_base_line_for_taxes_computation','_add_tax_details_in_base_line','profitability(','independent_profit(','independent_risk(','assess(','calculate('):check('Actual shared/native service '+service,service in engine)
if __name__=='__main__':
    import sys
    if '--freeze' in sys.argv:(r/'evidence/pr18-verified-source-sha256.json').write_text(json.dumps(ledger,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(status='PASS',checks=len(checks),source_files=len(ledger),source_hash=sha)))
