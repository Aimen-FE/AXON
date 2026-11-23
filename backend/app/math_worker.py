"""Fixed worker, never a Python interpreter for user code. stdin/stdout JSON only."""
import ast
import json
import math
import os
import resource
import sys

resource.setrlimit(resource.RLIMIT_CPU, (3, 4))
resource.setrlimit(resource.RLIMIT_AS, (768 * 1024**2, 768 * 1024**2))
resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))
resource.setrlimit(resource.RLIMIT_NOFILE, (32, 32))
resource.setrlimit(resource.RLIMIT_NPROC, (0, 0))
import sympy as s
from sympy import integrate, diff, simplify, solve, Poly
from sympy.polys.polyerrors import PolynomialError

SYMBOLS = {name:s.Symbol(name, real=True) for name in ('x','y','z','t')}
CONSTANTS = {'pi':s.pi,'e':s.E}
FUNCTIONS = {'sqrt':s.sqrt,'sin':s.sin,'cos':s.cos,'tan':s.tan,'log':s.log,'exp':s.exp,'abs':s.Abs}

# Load the deterministic operations before closing all filesystem/network/process access.
s.simplify(SYMBOLS['x']+1); s.solve(SYMBOLS['x']**2-4, SYMBOLS['x'])
s.integrate(SYMBOLS['x'], SYMBOLS['x']); s.diff(s.sin(SYMBOLS['x']), SYMBOLS['x'])
def deny_external(event, args):
    if event == 'open' or event.startswith(('socket.','subprocess.','os.exec','os.spawn','os.system','os.fork','os.listdir','os.scandir','os.remove','os.rename','os.mkdir')):
        raise PermissionError('Acceso externo deshabilitado')
sys.addaudithook(deny_external)

def expression(text):
    if not isinstance(text,str) or len(text)>500: raise ValueError('Expresión demasiado larga')
    tree = ast.parse(text.replace('^','**'), mode='eval')
    nodes = list(ast.walk(tree))
    if len(nodes)>100: raise ValueError('Expresión demasiado compleja')
    def build(node, depth=0):
        if depth>15: raise ValueError('Expresión demasiado profunda')
        sub=lambda n:build(n,depth+1)
        if isinstance(node,ast.Constant) and type(node.value) in (int,float):
            if not math.isfinite(node.value) or abs(node.value)>1e12: raise ValueError('Número fuera de rango')
            return s.Rational(str(node.value))
        if isinstance(node,ast.Name) and node.id in SYMBOLS: return SYMBOLS[node.id]
        if isinstance(node,ast.Name) and node.id in CONSTANTS: return CONSTANTS[node.id]
        if isinstance(node,ast.UnaryOp) and isinstance(node.op,(ast.UAdd,ast.USub)):
            value=sub(node.operand); return value if isinstance(node.op,ast.UAdd) else -value
        if isinstance(node,ast.BinOp) and isinstance(node.op,(ast.Add,ast.Sub,ast.Mult,ast.Div,ast.Pow)):
            if isinstance(node.op,ast.Pow):
                # Only literal, small powers. Nested power towers never get evaluated.
                exponent=node.right
                if isinstance(exponent,ast.UnaryOp) and isinstance(exponent.op,ast.USub) and isinstance(exponent.operand,ast.Constant): n=-exponent.operand.value
                elif isinstance(exponent,ast.Constant): n=exponent.value
                else: raise ValueError('La potencia requiere un exponente literal entre -12 y 12')
                if type(n) not in (int,float) or abs(n)>12: raise ValueError('Exponente fuera de rango')
                return sub(node.left)**s.Rational(str(n))
            left,right=sub(node.left),sub(node.right)
            if isinstance(node.op,ast.Add): return left+right
            if isinstance(node.op,ast.Sub): return left-right
            if isinstance(node.op,ast.Mult): return left*right
            if right==0: raise ValueError('División entre cero')
            return left/right
        if isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id in FUNCTIONS and len(node.args)==1 and not node.keywords:
            value=sub(node.args[0])
            if node.func.id=='exp' and value.is_number and abs(value)>100: raise ValueError('Exponencial fuera de rango')
            return FUNCTIONS[node.func.id](value)
        raise ValueError('Sintaxis no admitida. Usa números, x/y/z/t y funciones matemáticas disponibles')
    result=build(tree.body)
    if result.has(s.zoo,s.oo,-s.oo,s.nan): raise ValueError('Resultado indefinido o no finito')
    if result.is_number and result.is_real is False: raise ValueError('El cálculo numérico está limitado a números reales')
    return result

def run(body):
    op=body['operation']; variable=SYMBOLS[body['variable']]
    if op=='statistics':
        values=[s.Rational(str(v)) for v in body['values']]
        if not values or len(values)>500: raise ValueError('Lista de datos fuera de rango')
        values.sort(); count=len(values); mean=sum(values)/count
        median=values[count//2] if count%2 else (values[count//2-1]+values[count//2])/2
        variance=sum((v-mean)**2 for v in values)/count
        return {'count':count,'mean':str(mean),'median':str(median),'population_variance':str(variance),'population_stddev':str(s.sqrt(variance)),'min':str(values[0]),'max':str(values[-1])}
    expr=expression(body['expression'])
    if op=='verify':
        difference=simplify(expr-expression(body['comparison']))
        return {'equivalent':difference==0,'difference':str(difference),'scope':'Identidad simbólica en el dominio común; comprueba las restricciones del enunciado'}
    if op=='evaluate':
        if expr.free_symbols: raise ValueError('Para evaluar introduce números; usa simplificar si hay variables')
        result=expr
    elif op=='simplify': result=simplify(expr)
    elif op=='differentiate': result=diff(expr,variable)
    elif op=='integrate': result=integrate(expr,variable)
    elif op=='solve':
        try: polynomial=Poly(expr,variable)
        except PolynomialError: raise ValueError('Se resuelven ecuaciones polinómicas de grado 1 a 4; escribe el miembro izquierdo igualado a cero')
        if polynomial.degree()<1 or polynomial.degree()>4 or expr.free_symbols-{variable}: raise ValueError('Usa un polinomio de grado 1 a 4 con una sola incógnita')
        roots=solve(expr,variable)
        return {'solutions':[str(r) for r in roots],'verified':all(simplify(expr.subs(variable,r))==0 for r in roots),'domain':'real'}
    else: raise ValueError('Operación no disponible')
    text=str(result)
    if len(text)>5000: raise ValueError('Resultado demasiado extenso')
    out={'exact':text,'variable':str(variable)}
    if result.is_number and result.is_real:
        value=float(result.evalf(12))
        if math.isfinite(value): out['decimal']=value
    if op=='integrate': out.update(constant='C',verified=simplify(diff(result,variable)-expr)==0)
    if op=='differentiate': out['method']='Derivación simbólica determinista'
    return out

try:
    body=json.loads(sys.stdin.read(12000))
    print(json.dumps({'ok':True,'result':run(body)},ensure_ascii=False))
except Exception as exc:
    message=str(exc) if isinstance(exc,(ValueError,SyntaxError)) else 'La operación no puede completarse dentro del entorno limitado'
    print(json.dumps({'ok':False,'message':message[:300]},ensure_ascii=False))
