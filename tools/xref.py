# usage: xref.py <binary> <classdump> <sel1,sel2,...>   -> callers of objc_msgSend$sel stubs
import sys,re,struct,bisect
import array
import os; exec(open(os.path.join(os.path.dirname(os.path.abspath(__file__)),'objcdump.py')).read().split("a,sz,o = secs")[0])
imps=[]; names={}
cls=None
for l in open(sys.argv[2]):
    if l.startswith('@interface'): cls=l.split()[1]
    m=re.match(r'\s+([-+]) (\S+)\s+// (0x[0-9a-f]+)',l)
    if m: a=int(m.group(3),16); imps.append(a); names[a]=f'{m.group(1)}[{cls} {m.group(2)}]'
imps=sorted(set(imps))
def secrange(name):
    for k,v in secs.items():
        if k[1]==name: return v
a,sz,o=secrange('__objc_stubs'); want={}
sels=set(sys.argv[3].split(','))
for i in range(0,sz,32):
    w0,w1=struct.unpack_from('<II',data,o+i); pc=a+i
    if (w0&0x9f000000)==0x90000000:
        immlo=(w0>>29)&3; immhi=(w0>>5)&0x7ffff; imm=((immhi<<2)|immlo)
        if imm&(1<<20): imm-=1<<21
        tgt=(pc&~0xfff)+(imm<<12)+((w1>>10)&0xfff)*8
        try:
            s=cstr(ptr(tgt))
            if s in sels: want[pc]=s
        except Exception: pass
ta,tsz,to=secrange('__text')
arr=array.array('I'); arr.frombytes(data[to:to+tsz//4*4])
res={}
def gen():
    for i,w in enumerate(arr):
        if (w&0xfc000000)==0x94000000:
            imm=w&0x3ffffff
            if imm>=(1<<25): imm-=(1<<26)
            pc=ta+i*4; t=pc+imm*4
            if t in want: yield pc,t
for pc,t in gen():
    j=bisect.bisect_right(imps,int(pc))-1
    fn=names.get(imps[j],f'sub_{imps[j]:x}') if j>=0 else '?'
    res.setdefault(want[int(t)],[]).append((int(pc),fn))
for s in sels:
    print(f'### {s}: {len(res.get(s,[]))} callers')
    for pc,fn in sorted(set(res.get(s,[])),key=lambda x:x[0]): print(f'  {pc:#x}  {fn}')
