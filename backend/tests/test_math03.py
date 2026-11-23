import pytest

@pytest.mark.parametrize('operation,expression,expected',[
    ('evaluate','sqrt(16)+2/3',{'exact':'14/3'}),('simplify','(x+1)^2-x^2',{'exact':'2*x + 1'}),
    ('solve','x^2-4',{'solutions':['-2','2'],'verified':True}),('differentiate','x^3',{'exact':'3*x**2'}),
    ('integrate','x^2',{'exact':'x**3/3','verified':True,'constant':'C'})])
def test_math_real_worker(login,operation,expression,expected):
    r=login().post('/api/math',json={'operation':operation,'expression':expression});assert r.status_code==200,r.text
    assert r.json()['engine']=='sympy-restricted'
    assert all(r.json()['result'][k]==v for k,v in expected.items())

def test_statistics_and_equivalence(login):
    c=login();r=c.post('/api/math',json={'operation':'statistics','values':[1,2,3,4]});assert r.status_code==200
    assert r.json()['result']['mean']=='5/2' and r.json()['result']['population_variance']=='5/4'
    r=c.post('/api/math',json={'operation':'verify','expression':'(x+1)^2','comparison':'x^2+2*x+1'})
    assert r.json()['result']['equivalent'] is True

@pytest.mark.parametrize('expression',[
    '__import__("os").system("id")','open("/etc/passwd").read()','x.__class__','[i for i in range(5)]',
    '9^(9^9)','2^99999','1/0','lambda: 1','sqrt(-1)', 'globals()', '(x+1)'*120])
def test_rejects_code_towers_nonreal_and_unbounded(login,expression):
    assert login().post('/api/math',json={'expression':expression}).status_code==422
