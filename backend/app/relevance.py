"""Relevance gates shared by RAG and the tutor. Source attribution is explicit."""
import re,unicodedata
STOP=set('a al algo algun alguna algunos ante aqui asi aun bajo bien cada como con cual cuales cuando de del desde donde durante el ella ello ellos en entre era es esa ese eso esta estas este estos estoy fue ha hasta hay la las le les lo los mas me mi mis muy nada ni no nos o otra otro para pero por porque puede puedes que quien se segun ser si sin sobre son su sus te tener ti tiene todo tu tus un una uno unos y ya axon eres sabes instituto centro informacion dime necesito quiero dame perteneces'.split())

def norm(s):return ''.join(c for c in unicodedata.normalize('NFKD',s.lower()) if not unicodedata.combining(c))
def terms(s):return list(dict.fromkeys(t for t in re.findall(r'[^\W_]+',norm(s)) if len(t)>2 and t not in STOP))[:24]
def score(query,title,content):
    words=terms(query)
    if not words:return 0
    title=norm(title);body=norm(content)
    matched=[w for w in words if re.search(r'\b'+re.escape(w)+r'\w*',title+' '+body)]
    coverage=len(matched)/len(words)
    if not matched or (len(words)>=3 and coverage<.34):return 0
    return coverage*5+sum(1.5 if w in title else .3 for w in matched)

def attributed_citations(content,documents):
    used=[]
    for n in re.findall(r'\[fuente:(\d+)\]',content):
        index=int(n)-1
        if 0<=index<len(documents) and index not in used:used.append(index)
    citations=[{k:documents[i][k] for k in ('document_id','title','location','status')} for i in used]
    # Remove any forged marker, retain human-readable valid attribution.
    def mark(m):
        index=int(m[1])-1
        return f"({documents[index]['title']}, {documents[index]['location']})" if 0<=index<len(documents) else ''
    return re.sub(r'\[fuente:(\d+)\]',mark,content),citations
