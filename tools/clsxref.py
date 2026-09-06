import sys,re,struct,array,bisect
import os; exec(open(os.path.join(os.path.dirname(os.path.abspath(__file__)),'objcdump.py')).read().split("a,sz,o = secs")[0])
def secrange(name):
    for k,v in secs.items():
        if k[1]==name: return v
want=set(sys.argv[3].split(','))
# map classrefs addr -> class name
targets={}
a,sz,o=secrange('__objc_classrefs')
for i in range(0,sz,8):
    p=ptr(a+i)
    try:
        nm = p[1].replace('_OBJC_CLASS_$_','') if isinstance(p,tuple) else cstr(ptr(ro(p)+24))
    except Exception: continue
    if nm in want: targets[a+i]=nm
print('classrefs:',{hex(k):v for k,v in targets.items()})
imps=[];names={};cls=None
for l in open(sys.argv[2]):
    if l.startswith('@interface'): cls=l.split()[1]
    m=re.match(r'\s+([-+]) (\S+)\s+// (0x[0-9a-f]+)',l)
    if m: a_=int(m.group(3),16); imps.append(a_); names[a_]=f'{m.group(1)}[{cls} {m.group(2)}]'
imps=sorted(set(imps))
ta,tsz,to=secrange('__text'); arr=array.array('I'); arr.frombytes(data[to:to+tsz//4*4])
pages=set(t&~0xfff for t in targets); n=len(arr); res={}
for i in range(n):
    w=arr[i]
    if (w&0x9f000000)!=0x90000000: continue
    pc=ta+i*4
    immlo=(w>>29)&3; immhi=(w>>5)&0x7ffff; imm=(immhi<<2)|immlo
    if imm&(1<<20): imm-=1<<21
    page=(pc&~0xfff)+(imm<<12)
    if page not in pages: continue
    rd=w&0x1f
    for k in range(1,6):
        if i+k>=n: break
        w2=arr[i+k]
        if (w2&0xffc00000)==0xf9400000 and ((w2>>5)&0x1f)==rd:
            addr=page+((w2>>10)&0xfff)*8
            if addr in targets:
                j=bisect.bisect_right(imps,pc)-1
                res.setdefault(targets[addr],set()).add(names.get(imps[j],f'sub_{imps[j]:x}') if j>=0 else '?')
            break
        if (w2&0xff800000)==0x91000000 and ((w2>>5)&0x1f)==rd: break
for k,v in res.items():
    print('###',k); [print('  ',x) for x in sorted(v)]
