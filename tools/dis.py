# usage: dis.py <binary> <classdump.txt> <addr|Class:method> [maxbytes]
import sys, re, struct, subprocess, bisect
binpath, cdpath = sys.argv[1], sys.argv[2]
import os; exec(open(os.path.join(os.path.dirname(os.path.abspath(__file__)),'objcdump.py')).read().split("a,sz,o = secs")[0])
OBJDUMP='/Applications/Xcode.app/Contents/Developer/Toolchains/XcodeDefault.xctoolchain/usr/bin/llvm-objdump'
# collect IMPs from classdump
imps=[]; byname={}
cls=None
for l in open(cdpath):
    if l.startswith('@interface'): cls=l.split()[1]
    m=re.match(r'\s+[-+] (\S+)\s+// (0x[0-9a-f]+)',l)
    if m:
        a=int(m.group(2),16); imps.append(a); byname[f'{cls}:{m.group(1)}']=a
imps=sorted(set(imps))
def secrange(name):
    for k,v in secs.items():
        if k[1]==name: return v
    return None
def in_sec(addr,name):
    r=secrange(name); return r and r[0]<=addr<r[0]+r[1]
# stubs map
stubs={}
r=secrange('__stubs')
if r:
    a,sz,o=r
    for i in range(0,sz,12):
        w0,w1,w2=struct.unpack_from('<III',data,o+i)
        pc=a+i
        if (w0&0x9f000000)==0x90000000:
            immlo=(w0>>29)&3; immhi=(w0>>5)&0x7ffff; imm=((immhi<<2)|immlo)
            if imm&(1<<20): imm-=1<<21
            page=(pc&~0xfff)+(imm<<12)
            off12=((w1>>10)&0xfff)*8
            tgt=page+off12
            try:
                p=ptr(tgt); stubs[pc]=p[1] if isinstance(p,tuple) else f'{p:#x}'
            except Exception: pass
r=secrange('__objc_stubs')
if r:
    a,sz,o=r
    for i in range(0,sz,32):
        w0,w1=struct.unpack_from('<II',data,o+i); pc=a+i
        if (w0&0x9f000000)==0x90000000:
            immlo=(w0>>29)&3; immhi=(w0>>5)&0x7ffff; imm=((immhi<<2)|immlo)
            if imm&(1<<20): imm-=1<<21
            page=(pc&~0xfff)+(imm<<12); tgt=page+((w1>>10)&0xfff)*8
            try: stubs[pc]='objc_msgSend$'+cstr(ptr(tgt))
            except Exception: pass
def resolve_data(addr):
    try:
        if in_sec(addr,'__objc_selrefs'): return '@selector('+cstr(ptr(addr))+')'
        if in_sec(addr,'__objc_classrefs') or in_sec(addr,'__objc_superrefs'):
            p=ptr(addr)
            if isinstance(p,tuple): return p[1].replace('_OBJC_CLASS_$_','')
            return 'class '+cstr(ptr(ro(p)+24))
        if in_sec(addr,'__cfstring'): return '@"'+cstr(ptr(addr+16))+'"'
        if in_sec(addr,'__cstring') or in_sec(addr,'__objc_methname'): return '"'+cstr(addr)+'"'
        if in_sec(addr,'__got') or in_sec(addr,'__auth_got') or in_sec(addr,'__la_symbol_ptr'):
            p=ptr(addr); return '&'+(p[1] if isinstance(p,tuple) else f'{p:#x}')
        if in_sec(addr,'__objc_ivar'):
            return 'ivar_off=%d'%u32(addr)
    except Exception as e: return None
    return None
BODY='''start = byname[target] if ':' in target else int(target,16)
i=bisect.bisect_right(imps,start); end = imps[i] if i<len(imps) else start+0x800
maxb=int(sys.argv[4],16) if len(sys.argv)>4 else 0x1400
end=min(end,start+maxb)
out=subprocess.run([OBJDUMP,'-d','--no-show-raw-insn',f'--start-address={start:#x}',f'--stop-address={end:#x}',binpath],capture_output=True,text=True).stdout
regs={}
print(f'; ==== {target} @ {start:#x}..{end:#x}')
for l in out.splitlines():
    m=re.match(r'\s*([0-9a-f]+):\s+(\S+)\s*(.*)',l)
    if not m: continue
    pc=int(m.group(1),16); op=m.group(2); args=m.group(3)
    ann=''
    if op=='adrp':
        mm=re.match(r'(\w+),\s*(?:0x)?([0-9a-f]+)',args)
        if mm: regs[mm.group(1)]=int(mm.group(2),16)
    elif op in('add','ldr') :
        mm=re.match(r'(\w+),\s*\[?(\w+)(?:,\s*#(-?\d+))?\]?',args)
        if mm and mm.group(2) in regs:
            addr=regs[mm.group(2)]+int(mm.group(3) or 0)
            r=resolve_data(addr)
            if r: ann=f'  ; {r}'
            if op=='add': regs[mm.group(1)]=addr
            else: regs.pop(mm.group(1),None)
        elif mm: regs.pop(mm.group(1),None)
    elif op in('bl','b'):
        mm=re.match(r'0x([0-9a-f]+)',args)
        if mm:
            t=int(mm.group(1),16)
            if t in stubs: ann='  ; '+stubs[t]
            else:
                j=bisect.bisect_right(imps,t)-1
                if j>=0 and imps[j]==t:
                    nm=[k for k,v in byname.items() if v==t][:1]; ann='  ; '+(nm[0] if nm else '')
                else: ann=f'  ; sub_{t:x}'
    elif op=='mov':
        mm=re.match(r'(\w+),\s*(\w+)$',args)
        if mm and mm.group(2) in regs: regs[mm.group(1)]=regs[mm.group(2)]
        elif mm: regs.pop(mm.group(1),None)
    print(f'{pc:x}: {op} {args}{ann}')
'''
for target in sys.argv[3].split(','):
  exec(BODY)
