#!/usr/bin/env python3
"""Generate and verify wall/door playfield calling contracts."""

from __future__ import annotations
import argparse, csv, hashlib, json, re, subprocess
from pathlib import Path

ROM_BASE=0x40000
ROM_SHA1="decbe6438b3a2618bd7fe79d14be034efadd7ff4"

# address, name, arguments, return, exception, confidence, required opcodes
CONTRACTS=(
 (0x5EAB8,"pf_wall_draw","D0.w = x, D1.w = y","void","register wrapper; branches past stack loads into body shared with 0x5EAC2","Verified",("movem.l d2-d5/a2, -(a7)","move.w d0, d2","move.w d1, d3","bra.b 0x5eace","bsr.w 0x5e542")),
 (0x5EAC2,"pf_wall_draw_stack","uint16 x, uint16 y","void","shipped normal-stack entry with no discovered direct control site; shares body with 0x5EAB8","Verified",("move.w 0x1a(a7), d2","move.w 0x1e(a7), d3","lea.l 0x903800.l, a1","move.w d0, 0x82(a2)")),
 (0x5F024,"wall_place_playfield_update","D0.w = x, D1.w = y","void","register entry","Verified",("move.w d0, d2","move.w d1, d3","lea.l 0x903800.l, a1","bsr.w 0x5fc46","move.w d0, 0x82(a2)")),
 (0x5F2C0,"maze_init_walls","void","void","32x32 initialization pass","Verified",("btst.b 0x7, 0x90491d.l","cmpi.w 0x270f, 0x904004.l","cmpi.w 0x8003, -0x2(a2)","bsr.w 0x5eab8")),
 (0x5F310,"mob_place_tile","D0.w = packed maze slot, D1.w = new object type","void","register wrapper; branches past stack loads into body shared with pf_replace","Verified",("move.w d0, d2","move.w d1, d3","bra.b 0x5f32e","bsr.w 0x5ddda","bsr.w 0x5f5a0")),
 (0x5F31E,"pf_replace","uint16 packed_maze_slot, uint16 new_object_type","void","normal-stack entry to body shared with mob_place_tile","Verified",("move.w 0x22(a7), d2","move.w 0x26(a7), d3","lea.l 0x902000.l, a2","bsr.w 0x5f7f0","bsr.w 0x5f5a0")),
 (0x5F598,"refresh_tile_visual_stack","uint16 packed maze slot, uint16 object type","void","frameless normal-stack wrapper falling through to refresh_tile_visual","Verified",("move.w 0x6(a7), d0","move.w 0xa(a7), d1","lea.l 0x5ea2e.l, a2","bsr.w 0x5eab8","jsr (a2)","rts")),
 (0x5F5A0,"refresh_tile_visual","D0.w = packed maze slot, D1.w = object type","void","register dispatcher; calls pf_isblankfloor indirectly through fixed A2=0x5EA2E","Verified",("lea.l 0x5ea2e.l, a2","move.w d0, d2","move.w d0, d3","bsr.w 0x5eab8","jsr (a2)")),
 (0x5F644,"refresh_tile_visual_legacy","D0.w = packed maze slot, D1.w = object type","void","unreferenced shipped register entry; legacy two-way type-2 wall versus floor dispatcher sharing the main redraw epilogue","Strong inference",("movem.l d2-d3/a2, -(a7)","lea.l 0x5ea2e.l, a2","cmpi.w 0x2, d1","bsr.w 0x5eab8","jsr (a2)","rts")),
 (0x5F772,"pf_isdoor_stack","uint16 x, uint16 y","D0.l = door class 1, 2, or 3; 0 when not a door","frameless stack wrapper falling through to register body","Verified",("move.w 0x6(a7), d0","move.w 0xa(a7), d1","cmpi.w 0x9d18, d0","moveq 0x3, d0","moveq 0x0, d0")),
 (0x5F77A,"pf_isdoor","D0.w = x, D1.w = y","D0.l = door class 1, 2, or 3; 0 when not a door","register body","Verified",("andi.w 0x1f, d0","cmpi.w 0x9d3c, d0","cmpi.w 0x9d7c, d0","moveq 0x1, d0","moveq 0x0, d0")),
 (0x5F7C0,"maze_doors_setup","void","void","32x31 initial draw pass; x begins at 1","Verified",("moveq 0x1, d2","clr.l d3","bsr.w 0x5f77a","bsr.w 0x5f876","cmpi.w 0x20, d2")),
 (0x5F7F0,"pf_door_update_surrounding_xy","D0.w = x, D1.w = y","void","register wrapper; branches past stack loads into body shared with 0x5F7FA","Verified",("move.w d0, d2","move.w d1, d3","bra.b 0x5f806","bsr.w 0x5f77a","bsr.w 0x5f876")),
 (0x5F7FA,"pf_door_update_surrounding","uint16 x, uint16 y","void","normal-stack entry to shared four-neighbor redraw body","Verified",("move.w 0x16(a7), d2","move.w 0x1a(a7), d3","andi.l 0x1f, d2","bsr.w 0x5f77a","bsr.w 0x5f876")),
 (0x5F876,"pf_door_draw_xy","A0.w = x, A1.w = y, D0.w = door class","void","register wrapper; branches past stack loads into body shared with 0x5F880","Verified",("move.w a0, d2","move.w a1, d3","bra.b 0x5f890","lea.l 0x5f77a.l, a2","jsr (a2)")),
 (0x5F880,"pf_door_draw","uint16 x, uint16 y, uint16 door_class","void","normal-stack entry; calls pf_isdoor indirectly through fixed A2=0x5F77A","Verified",("move.w 0x1a(a7), d2","move.w 0x1e(a7), d3","move.w 0x22(a7), d0","lea.l 0x5f77a.l, a2","addi.w 0x1400, d1")),
)

def direct_sites(rom):
    found={a:[] for a,*_ in CONTRACTS}
    for o in range(0,len(rom)-6,2):
        op=int.from_bytes(rom[o:o+2],"big"); target=None
        if op in (0x4EB9,0x4EF9): target=int.from_bytes(rom[o+2:o+6],"big")
        elif op==0x6100: target=ROM_BASE+o+2+int.from_bytes(rom[o+2:o+4],"big",signed=True)
        elif op>>8==0x61 and op&0xff not in (0,0xff): target=ROM_BASE+o+2+int.from_bytes(bytes((op&0xff,)),"big",signed=True)
        if target in found: found[target].append(ROM_BASE+o)
    return {a:sorted(set(v)) for a,v in found.items()}

def body(root,loader,a):
    analysis = (
        "pDj 0x312 @ 0x5eac2"
        if a == 0x5EAC2
        else f"af- 0x{a:x}; af @ 0x{a:x}; pdfj @ 0x{a:x}"
    )
    cmd=["r2","-q","-n","-e","scr.color=0","-i",str(loader),"-c",analysis,"-c","q","malloc://1"]
    r=subprocess.run(cmd,cwd=root,text=True,capture_output=True)
    if r.returncode or re.search(r"(?im)^(?:ERROR|FATAL)",r.stderr): raise SystemExit(f"radare2 body audit failed at 0x{a:X}:\n{r.stderr}")
    parsed=json.loads(r.stdout)
    operations=parsed if isinstance(parsed,list) else parsed.get("ops",[])
    return [x["opcode"] for x in operations]

def runtime_check(root):
    loader=root/"doc"/"gauntlet_loader.r2"
    for a,n,_,_,_,_,required in CONTRACTS:
        ops=body(root,loader,a)
        for expected in required:
            if expected not in ops: raise SystemExit(f"{n}: required instruction absent: {expected}")
        if "rts" not in ops: raise SystemExit(f"{n}: analyzed body has no RTS/shared return")
    print(f"wall/door contracts: analyzed {len(CONTRACTS)} entries; ABI evidence matches")

def main():
    p=argparse.ArgumentParser(); p.add_argument("--check",action="store_true"); p.add_argument("--run-check",action="store_true"); args=p.parse_args()
    here=Path(__file__).resolve().parent; root=here.parent.parent; rom=(root/"row76.bin").read_bytes()
    if len(rom)!=0x20000 or hashlib.sha1(rom).hexdigest()!=ROM_SHA1: raise SystemExit("row76.bin is not the documented 128 KiB target ROM")
    sites=direct_sites(rom); rows=[{"address":f"0x{a:05X}","name":n,"arguments":i,"return":ret,"exceptional_convention":c,"direct_control_sites":";".join(f"0x{x:05X}" for x in sites[a]),"confidence":conf} for a,n,i,ret,c,conf,_ in CONTRACTS]
    out=here/"wall_door_contracts.csv"
    if args.check:
        with out.open(newline="") as f: old=list(csv.DictReader(f))
        if old!=rows: raise SystemExit("wall_door_contracts.csv is stale; regenerate it")
        print(f"wall_door_contracts.csv: verified {len(rows)} entries")
    else:
        with out.open("w",newline="") as f: w=csv.DictWriter(f,fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
        print(f"wrote {len(rows)} rows to {out}")
    if args.run_check: runtime_check(root)

if __name__=="__main__": main()
