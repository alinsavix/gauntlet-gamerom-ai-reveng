#!/usr/bin/env python3
"""Generate and verify playfield stamp, visibility, and floor contracts."""

from __future__ import annotations
import argparse, csv, hashlib, json, re, subprocess
from pathlib import Path

ROM_BASE = 0x40000
ROM_SHA1 = "decbe6438b3a2618bd7fe79d14be034efadd7ff4"

# address, name, arguments, return, exceptional convention, confidence, opcodes
CONTRACTS = (
 (0x5E536,"pf_stamp_update","uint16 packed_position, const uint16 *descriptor4, uint16 addend","void","frameless normal-stack leaf","Verified",("move.w 0x6(a7), d0","movea.l 0x8(a7), a0","movea.w 0xe(a7), a1","move.w d0, 0x82(a1)")),
 (0x5E542,"pf_stamp_update_regs","D0.w = packed position, A0 = four-word descriptor, A1.w = addend","void","register entry shared by floor/wall/tile renderers","Verified",("move.w d0, d1","addi.l 0x900000, d0","move.w d0, 0x82(a1)")),
 (0x5E57E,"tile_on_screen_d4","D4.w = packed maze position","D0.l = -1 when on screen, else 0","register wrapper; tail-branches into shared saved-register body","Verified",("movem.l d2/d4, -(a7)","bra.b 0x5e58c","moveq 0xff, d0")),
 (0x5E584,"tile_on_screen_test","uint16 packed_maze_position","D0.l = -1 when on screen, else 0","normal-stack wrapper sharing body with 0x5E57E","Verified",("move.w 0xe(a7), d4","move.w 0x6c00, d1","move.w 0x7000, d1","moveq 0xff, d0")),
 (0x5E5D2,"tile_near_screen_d4","D4.w = packed maze position","D0.l = -1 when near the screen, else 0","register wrapper; tail-branches into shared saved-register body","Verified",("movem.l d2/d4, -(a7)","bra.b 0x5e5e0","moveq 0xff, d0")),
 (0x5E5D8,"tile_near_screen_test","uint16 packed_maze_position","D0.l = -1 when near the screen, else 0","normal-stack wrapper; called indirectly through A2 by dragon visibility code","Verified",("move.w 0xe(a7), d4","move.w 0x7b80, d1","move.w 0x7f80, d1","moveq 0xff, d0")),
 (0x5E7A6,"maze_place_object_types","uint8 object_type","D0.l = 1 only when a slot of type-3 was found; plain-type matches are stamped without setting the result","frameless; reads low byte of first stack slot at A7+0x1B after saving registers","Verified",("move.b 0x1b(a7), d2","addi.b 0xfd, d3","bsr.w 0x5e5d2","bsr.w 0x5f310","move.l d5, d0")),
 (0x5E80C,"maze_convert_walls_to_exits","void","D0.l = 1 when any eligible wall was converted, else 0","","Verified",("moveq 0x40, d3","cmpi.w 0x20f6, d0","move.w 0x10, d1","bsr.w 0x5f310","move.l d2, d0")),
 (0x5E868,"maze_special_floor","void","void","","Verified",("lea.l 0x902000.l, a0","cmpi.w 0x8003, d0","move.w d1, -0x2(a0)","cmpa.l 0x902800, a0")),
 (0x5E888,"pf_floor_draw_xy","D0.w = x, D1.w = y","void","register wrapper; branches past the normal-stack argument loads in 0x5E892","Verified",("movem.l d2-d6, -(a7)","move.w d0, d2","move.w d1, d3","bra.b 0x5e89e","bsr.w 0x5e542")),
 (0x5E892,"pf_floor_update","uint16 x, uint16 y","void","normal-stack entry to shared floor-rendering body","Verified",("move.w 0x1a(a7), d2","move.w 0x1e(a7), d3","lea.l 0x5ba70.l, a0","bsr.w 0x5e542","bsr.w 0x5ea66")),
 (0x5EA00,"maze_floor_decor","void","void","32x32 loop calling register entry 0x5E888","Verified",("clr.l d3","clr.l d2","bsr.w 0x5e888","cmpi.w 0x20, d3")),
 (0x5EA26,"pf_isblankfloor_stack","uint16 x, uint16 y","D0.l = -1 for eligible blank floor, else 0","unreferenced stack wrapper; falls through into register body 0x5EA2E","Verified",("move.w 0x6(a7), d0","move.w 0xa(a7), d1","cmpi.w 0x8000, (a0, d1.w)","moveq 0xff, d0")),
 (0x5EA2E,"pf_isblankfloor","D0.w = x, D1.w = y","D0.l = -1 when x & 0x1F == 0 (column-0 short circuit) or when picture is 0x8000 and object type is not 0x3F; else 0","register body; also entered by fall-through from 0x5EA26","Verified",("andi.w 0x1f, d0","cmpi.w 0x8000, (a0, d1.w)","cmpi.b 0x3f, d0","moveq 0xff, d0","moveq 0x0, d0")),
 (0x5EA66,"pf_is_connectable_floor_xy","D0.w = x, D1.w = y","D0.l = -1 for a connectable floor neighbor, else 0","register entry sharing the -1/0 return leaves at 0x5EA5E/0x5EA62","Verified",("andi.w 0x1f, d0","cmpi.w 0x8000, (a0, d1.w)","andi.l 0x80000800, d1","cmpi.b 0x7, d0","bra.b 0x5ea5e")),
)

def direct_sites(rom: bytes):
    found={a:[] for a,*_ in CONTRACTS}
    for o in range(0,len(rom)-6,2):
        op=int.from_bytes(rom[o:o+2],"big"); target=None
        if op in (0x4EB9,0x4EF9): target=int.from_bytes(rom[o+2:o+6],"big")
        elif op==0x6100: target=ROM_BASE+o+2+int.from_bytes(rom[o+2:o+4],"big",signed=True)
        elif op>>8==0x61 and op&0xff not in (0,0xff): target=ROM_BASE+o+2+int.from_bytes(bytes((op&0xff,)),"big",signed=True)
        if target in found: found[target].append(ROM_BASE+o)
    return {a:sorted(set(s)) for a,s in found.items()}

def body(root, loader, address):
    cmd=["r2","-q","-n","-e","scr.color=0","-i",str(loader),"-c",f"af- 0x{address:x}; af @ 0x{address:x}; pdfj @ 0x{address:x}","-c","q","malloc://1"]
    r=subprocess.run(cmd,cwd=root,text=True,capture_output=True)
    if r.returncode or re.search(r"(?im)^(?:ERROR|FATAL)",r.stderr): raise SystemExit(f"radare2 body audit failed at 0x{address:X}:\n{r.stderr}")
    return [op["opcode"] for op in json.loads(r.stdout).get("ops",[])]

def runtime_check(root):
    loader=root/"doc"/"gauntlet_loader.r2"
    for address,name,_,_,_,_,required in CONTRACTS:
        ops=body(root,loader,address)
        for expected in required:
            if expected not in ops: raise SystemExit(f"{name}: required instruction absent: {expected}")
        if "rts" not in ops: raise SystemExit(f"{name}: analyzed body has no RTS/shared return")
    print(f"playfield/floor contracts: analyzed {len(CONTRACTS)} entries; ABI evidence matches")

def main():
    p=argparse.ArgumentParser(); p.add_argument("--check",action="store_true"); p.add_argument("--run-check",action="store_true"); args=p.parse_args()
    here=Path(__file__).resolve().parent; root=here.parent.parent; rom=(root/"row76.bin").read_bytes()
    if len(rom)!=0x20000 or hashlib.sha1(rom).hexdigest()!=ROM_SHA1: raise SystemExit("row76.bin is not the documented 128 KiB target ROM")
    sites=direct_sites(rom)
    rows=[{"address":f"0x{a:05X}","name":n,"arguments":i,"return":ret,"exceptional_convention":c,"direct_control_sites":";".join(f"0x{x:05X}" for x in sites[a]),"confidence":conf} for a,n,i,ret,c,conf,_ in CONTRACTS]
    out=here/"playfield_floor_contracts.csv"
    if args.check:
        with out.open(newline="") as f: old=list(csv.DictReader(f))
        if old!=rows: raise SystemExit("playfield_floor_contracts.csv is stale; regenerate it")
        print(f"playfield_floor_contracts.csv: verified {len(rows)} entries")
    else:
        with out.open("w",newline="") as f: w=csv.DictWriter(f,fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
        print(f"wrote {len(rows)} rows to {out}")
    if args.run_check: runtime_check(root)

if __name__=="__main__": main()
