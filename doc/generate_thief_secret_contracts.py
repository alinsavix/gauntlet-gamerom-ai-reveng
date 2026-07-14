#!/usr/bin/env python3
"""Generate and verify final thief-state and secret-room callable contracts."""

from __future__ import annotations
import argparse, csv, hashlib, json, re, subprocess
from pathlib import Path

ROM_BASE=0x40000
ROM_SHA1="decbe6438b3a2618bd7fe79d14be034efadd7ff4"

# address, name, arguments, return, exception, confidence, size, required opcodes
CONTRACTS=(
 (0x486FE,"secret_check","void","void","normal stack; level-transition secret interval bookkeeping only","Verified",0x56,("tst.b 0x904065.l","tst.b 0x904063.l","move.w 0x904000.l, 0x904870.l","addi.w 0xf, (a0)","move.w 0x28, (a0)","subq.w 0x2, (a0)","move.w 0x4, (a0)","move.w (a0), 0x904878.l","rts")),
 (0x4E172,"thief_end_dodge","void","void","normal stack; if an active dodge exists, clears mode bit 3, toggles low mode bits 0/1, and repairs the next route cell","Verified",0x46,("tst.w 0x904ba4.l","btst.b 0x3, 0x1(a0)","andi.w 0xfff7, (a0)","eori.w 0x3, (a0)","jsr 0x4f912.l","move.w 0x904ba2.l, 0x904ba6.l","rts")),
 (0x4E1B8,"thief_begin_dodge","void","void","normal stack; if an active non-dodging thief exists, sets mode bit 3, toggles low mode bits 0/1, and repairs the next route cell","Verified",0x46,("tst.w 0x904ba4.l","btst.b 0x3, 0x1(a0)","ori.w 0x8, (a0)","eori.w 0x3, (a0)","jsr 0x4f912.l","move.w 0x904ba2.l, 0x904ba6.l","rts")),
 (0x4E630,"thief_track_victim_move","uint16 new_packed_pos, uint16 player_index","void","normal stack; updates only when player_index is the current thief victim and the packed position changed","Verified",0x54,("move.w 0xa(a6), d2","move.w 0xe(a6), d0","cmp.w 0x904b9a.l, d0","cmp.w (a2), d2","jsr 0x510fc.l","jsr 0x50fd2.l","move.w d2, (a2)","rts")),
 (0x4FCF0,"thief_find_aligned_shooter","void","D0.l = player index 0-3; -1 when none","normal stack; scans active player MOBs whose shot direction is opposite thief direction and whose wrapped position lies exactly on that shot ray","Verified",0x1C2,("move.w 0x904ba4.l, d0","move.w 0x904b9c.l, d1","eor.l d1, d0","cmp.l d0, d1","divs.w 0x10, d0","jmp 0x4fe08(pc, d0.w)","cmpi.w 0x4, d6","moveq 0xff, d0","move.w d6, d0","ext.l d0","rts")),
 (0x54BE0,"secret_code_build","void","void","frameless; uses global name/state buffers and preserves D2","Verified",0xC6,("lea.l 0x904aa4.l, a0","lea.l 0x54cc6.l, a1","cmpi.b 0x20, d2","lea.l 0x54ca6.l, a1","move.b 0x2d, 0x3(a0)","or.w 0x904870.l, d2","clr.b 0x7(a0)","rts")),
 (0x54EC6,"secret_getname","void","void","normal stack; global winner/settings state; either initializes name entry or marks the winner complete and clears trick_player","Verified",0x122,("movea.l 0x904063, a2","movea.l 0x904aa4, a1","andi.l 0x2000, d0","move.b 0x20, (a0, d0.w)","move.b 0x41, (a1)","jsr 0x25a.l","jsr 0x218.l","jsr 0x200.l","jsr 0x142.l","move.b 0x2, (a0, d0.w)","move.b 0xff, (a2)","rts")),
)

def direct_sites(rom):
 found={row[0]:[] for row in CONTRACTS}
 for off in range(0,len(rom)-6,2):
  op=int.from_bytes(rom[off:off+2],"big"); target=None
  if op in (0x4EB9,0x4EF9): target=int.from_bytes(rom[off+2:off+6],"big")
  elif op==0x6100: target=ROM_BASE+off+2+int.from_bytes(rom[off+2:off+4],"big",signed=True)
  elif op>>8==0x61 and op&0xff not in (0,0xff): target=ROM_BASE+off+2+int.from_bytes(bytes((op&0xff,)),"big",signed=True)
  if target in found: found[target].append(ROM_BASE+off)
 return {a:sorted(set(v)) for a,v in found.items()}

def opcodes(root,loader,address,size):
 cmd=["r2","-q","-n","-e","scr.color=0","-i",str(loader),"-c",f"pDj {size} @ 0x{address:x}","-c","q","malloc://1"]
 result=subprocess.run(cmd,cwd=root,text=True,capture_output=True)
 if result.returncode or re.search(r"(?im)^(?:ERROR|FATAL)",result.stderr): raise SystemExit(f"radare2 thief/secret audit failed at 0x{address:X}:\n{result.stderr}")
 return [item["opcode"] for item in json.loads(result.stdout)]

def runtime_check(root):
 loader=root/"doc"/"gauntlet_loader.r2"
 for address,name,_,_,_,_,size,required in CONTRACTS:
  operations=opcodes(root,loader,address,size)
  for expected in required:
   if expected not in operations: raise SystemExit(f"{name} (0x{address:X}): required instruction absent: {expected}")
 print(f"thief/secret contracts: analyzed {len(CONTRACTS)} entries; ABI evidence matches")

def main():
 parser=argparse.ArgumentParser(); parser.add_argument("--check",action="store_true"); parser.add_argument("--run-check",action="store_true"); args=parser.parse_args()
 here=Path(__file__).resolve().parent; root=here.parent; rom=(root/"row76.bin").read_bytes()
 if len(rom)!=0x20000 or hashlib.sha1(rom).hexdigest()!=ROM_SHA1: raise SystemExit("row76.bin is not the documented 128 KiB target ROM")
 sites=direct_sites(rom)
 rows=[{"address":f"0x{a:05X}","name":n,"arguments":arguments,"return":ret,"exceptional_convention":exception,"direct_control_sites":";".join(f"0x{x:05X}" for x in sites[a]),"confidence":confidence} for a,n,arguments,ret,exception,confidence,_,_ in CONTRACTS]
 output=here/"thief_secret_contracts.csv"
 if args.check:
  with output.open(newline="") as handle: old=list(csv.DictReader(handle))
  if old!=rows: raise SystemExit("thief_secret_contracts.csv is stale; regenerate it")
  print(f"thief_secret_contracts.csv: verified {len(rows)} entries")
 else:
  with output.open("w",newline="") as handle: writer=csv.DictWriter(handle,fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)
  print(f"wrote {len(rows)} rows to {output}")
 if args.run_check: runtime_check(root)

if __name__=="__main__": main()
