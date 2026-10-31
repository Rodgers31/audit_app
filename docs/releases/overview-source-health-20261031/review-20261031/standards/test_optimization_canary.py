"""Negative assertion control; explicit optimization check cannot be stripped."""
import hashlib,json,os,pathlib,sys

def test_runtime_is_optimized_and_test_module_is_rewritten(request):
    if sys.flags.optimize != 1 or __debug__:
        raise RuntimeError('The exact run must use Python -O')
    modules={}
    for item in request.session.items:
        module=sys.modules[item.function.__module__]
        name=pathlib.Path(getattr(module,'__file__','')).name
        if name in ('test_optimization_canary.py','test_backend_independent.py'):
            data={'file':module.__file__,'loader':type(module.__loader__).__name__,'optimize':sys.flags.optimize,'debug':__debug__}
            helper=getattr(module,'denied',None)
            if helper is not None:
                data['denied_code_names']=list(helper.__code__.co_names)
                data['denied_rewritten']=any(n.startswith('@pytest') for n in helper.__code__.co_names)
                if not data['denied_rewritten']:raise RuntimeError('Original denied helper was not rewritten')
            modules[module.__name__]=data
    pathlib.Path('/evidence/'+os.environ['ASSERTION_PROBE_LABEL']+'-runtime.json').write_text(json.dumps({'python':sys.version,'optimize':sys.flags.optimize,'debug':__debug__,'modules':modules},indent=2)+'\n')

def test_false_assert_cannot_silently_pass():
    if sys.flags.optimize != 1:raise RuntimeError('Not optimized')
    assert False, 'EXPECTED_REWRITTEN_FALSE_ASSERT'
