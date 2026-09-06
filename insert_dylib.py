# Add a weak LC_LOAD_DYLIB to an arm64 Mach-O (uses header padding before the first section).
import sys, struct
path, dylib = sys.argv[1], sys.argv[2]
d = bytearray(open(path, 'rb').read())
magic, cputype, cpusub, ftype, ncmds, sizeofcmds, flags, _ = struct.unpack_from('<IiiIIIII', d, 0)
assert magic == 0xfeedfacf, 'not a 64-bit Mach-O'
off = 32; first_sect = None
for _ in range(ncmds):
    cmd, csz = struct.unpack_from('<II', d, off)
    if cmd == 0x19:  # LC_SEGMENT_64
        segname = d[off+8:off+24].rstrip(b'\0'); nsects = struct.unpack_from('<I', d, off+64)[0]
        so = off + 72
        for _ in range(nsects):
            sect_off = struct.unpack_from('<I', d, so+48)[0]
            if sect_off and (first_sect is None or sect_off < first_sect): first_sect = sect_off
            so += 80
    if cmd in (0xc, 0x18) and d[off+8+struct.unpack_from('<I', d, off+8)[0]:off+csz].split(b'\0')[0] == dylib.encode():
        print('already present'); sys.exit(0)
    off += csz
name = dylib.encode() + b'\0'
csz = (24 + len(name) + 7) & ~7
end = 32 + sizeofcmds
assert end + csz <= first_sect, f'no header space: need {csz}, have {first_sect-end}'
lc = struct.pack('<IIIIII', 0x80000018, csz, 24, 0, 0, 0) + name.ljust(csz-24, b'\0')  # LC_LOAD_WEAK_DYLIB
d[end:end+csz] = lc
struct.pack_into('<II', d, 16, ncmds+1, sizeofcmds+csz)
open(path, 'wb').write(d); print(f'added LC_LOAD_WEAK_DYLIB {dylib} ({csz} bytes)')
