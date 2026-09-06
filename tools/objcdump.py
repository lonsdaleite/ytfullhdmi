import sys, struct, re
from macholib.MachO import MachO
from macholib.mach_o import LC_SEGMENT_64, LC_DYLD_CHAINED_FIXUPS

path = sys.argv[1]
data = open(path,'rb').read()
m = MachO(path); h = m.headers[0]
segs=[]; secs={}; fix=None
for lc, cmd, extra in h.commands:
    if lc.cmd == LC_SEGMENT_64:
        segs.append((cmd.vmaddr, cmd.vmsize, cmd.fileoff))
        for s in extra:
            secs[(cmd.segname.rstrip(b'\0').decode(), s.sectname.rstrip(b'\0').decode())]=(s.addr,s.size,s.offset)
    elif lc.cmd == LC_DYLD_CHAINED_FIXUPS:
        fix=(cmd.dataoff, cmd.datasize)
BASE = [va for va,vs,fo in segs if fo==0 and va][0]
def off(addr):
    for va,vs,fo in segs:
        if va <= addr < va+vs: return fo + (addr-va)
    raise KeyError(hex(addr))
# chained fixups: pointer format + imports
ptr_format=2; imports=[]
if fix:
    fo=fix[0]
    ver,starts_off,imports_off,symbols_off,imports_count,imports_format,symbols_format = struct.unpack_from('<7I',data,fo)
    seg_count = struct.unpack_from('<I',data,fo+starts_off)[0]
    seg_offs = struct.unpack_from('<%dI'%seg_count,data,fo+starts_off+4)
    for so in seg_offs:
        if so:
            size,page_size,pf = struct.unpack_from('<IHH',data,fo+starts_off+so); ptr_format=pf; break
    for i in range(imports_count):
        if imports_format==1:
            v=struct.unpack_from('<I',data,fo+imports_off+4*i)[0]; name_off=v>>9
        elif imports_format==2:
            v=struct.unpack_from('<I',data,fo+imports_off+8*i)[0]; name_off=v>>9
        else:
            v=struct.unpack_from('<Q',data,fo+imports_off+16*i)[0]; name_off=v>>32
        so=fo+symbols_off+name_off; e=data.index(b'\0',so); imports.append(data[so:e].decode(errors='replace'))
def ptr(addr):
    v=struct.unpack_from('<Q',data,off(addr))[0]
    if not fix or v==0: return v
    if v>>63:  # bind
        ord_=v & 0xffffff
        return ('bind', imports[ord_] if ord_<len(imports) else '?')
    target=v & 0xfffffffff; high8=(v>>36)&0xff
    if ptr_format==6: return BASE+target
    return target | (high8<<56)
def cstr(addr):
    if isinstance(addr,tuple): return addr[1]
    if not addr: return ''
    o=off(addr); e=data.index(b'\0',o); return data[o:e].decode(errors='replace')
def u32(addr): return struct.unpack_from('<I',data,off(addr))[0]
def methods(ml):
    if not ml or isinstance(ml,tuple): return []
    ent=u32(ml); cnt=u32(ml+4); out=[]
    if ent & 0x80000000:
        es=ent & 0xffff
        for i in range(cnt):
            e=ml+8+i*es
            n,t,imp=struct.unpack_from('<iii',data,off(e))
            out.append((cstr(ptr(e+n)), e+8+imp))
    else:
        es=ent & 0xffff
        for i in range(cnt):
            e=ml+8+i*es
            out.append((cstr(ptr(e)), ptr(e+16)))
    return out
def ivars(il):
    if not il or isinstance(il,tuple): return []
    ent=u32(il); cnt=u32(il+4); out=[]
    for i in range(cnt):
        e=il+8+i*ent
        out.append((cstr(ptr(e+8)), cstr(ptr(e+16))))
    return out
def protos(pl):
    if not pl or isinstance(pl,tuple): return []
    cnt=struct.unpack_from('<Q',data,off(pl))[0]; out=[]
    for i in range(cnt):
        p=ptr(pl+8+8*i)
        if isinstance(p,tuple): out.append(p[1]); continue
        out.append(cstr(ptr(p+8)))
    return out
def ro(cls):
    d=ptr(cls+32)
    if isinstance(d,tuple): return None
    return d & ~0x7
def dump_class(cls):
    r=ro(cls)
    if r is None: return None
    name=cstr(ptr(r+24))
    sup=ptr(cls+8); supn = sup[1] if isinstance(sup,tuple) else (cstr(ptr(ro(sup)+24)) if sup else 'nil')
    meta=ptr(cls); cm = methods(ptr(ro(meta)+32)) if not isinstance(meta,tuple) else []
    return dict(name=name, super=supn, protos=protos(ptr(r+40)), ivars=ivars(ptr(r+48)), im=methods(ptr(r+32)), cm=cm)
a,sz,o = secs[('__DATA_CONST','__objc_classlist')] if ('__DATA_CONST','__objc_classlist') in secs else secs[('__DATA','__objc_classlist')]
pat = re.compile(sys.argv[2]) if len(sys.argv)>2 else None
out=sys.stdout
for i in range(sz//8):
    cls=ptr(a+8*i)
    try: c=dump_class(cls)
    except Exception as ex: continue
    if not c: continue
    if pat and not pat.search(c['name']): continue
    print(f"@interface {c['name']} : {c['super']} <{', '.join(c['protos'])}>")
    for n,t in c['ivars']: print(f"  ivar {n} {t}")
    for n,imp in c['cm']: print(f"  + {n}  // {imp:#x}")
    for n,imp in c['im']: print(f"  - {n}  // {imp:#x}")
    print("@end")
# categories
key=('__DATA_CONST','__objc_catlist') if ('__DATA_CONST','__objc_catlist') in secs else ('__DATA','__objc_catlist')
if key in secs:
    a,sz,o=secs[key]
    for i in range(sz//8):
        cat=ptr(a+8*i)
        try:
            cn=cstr(ptr(cat)); cl=ptr(cat+8)
            cln = cl[1] if isinstance(cl,tuple) else cstr(ptr(ro(cl)+24))
            if pat and not (pat.search(cln) or pat.search(cn)): continue
            print(f"@interface {cln} ({cn})")
            for n,imp in methods(ptr(cat+24)): print(f"  + {n}  // {imp:#x}")
            for n,imp in methods(ptr(cat+16)): print(f"  - {n}  // {imp:#x}")
            print("@end")
        except Exception as ex: pass
