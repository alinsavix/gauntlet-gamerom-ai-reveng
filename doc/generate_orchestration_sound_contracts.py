#!/usr/bin/env python3
"""Generate and verify reset/VBLANK, main-loop, sound-ring, and alpha contracts."""

from __future__ import annotations
import argparse, csv, hashlib, json, re, subprocess
from pathlib import Path

ROM_BASE=0x40000
ROM_SHA1="decbe6438b3a2618bd7fe79d14be034efadd7ff4"

# address, name, arguments, return, exception, confidence, size, required opcodes
CONTRACTS=(
 (0x40000,"game_start_veneer","void","does not return","six-byte OS hook; tail-jumps to game_start","Verified",0x6,("jmp 0x4014c.l",)),
 (0x40006,"game_vblank_veneer","interrupt frame only","no value; target exits with RTE","six-byte OS IRQ hook; tail-jumps to game_vblank","Verified",0x6,("jmp 0x4017e.l",)),
 (0x4000C,"game_irq1_watchdog_trap","interrupt frame only","does not return","six-byte self-JMP trap; unexpected IRQ1 stops watchdog service","Verified",0x6,("jmp 0x4000c.l",)),
 (0x40012,"game_irq3_watchdog_trap","interrupt frame only","does not return","six-byte self-JMP trap; unexpected IRQ3 stops watchdog service","Verified",0x6,("jmp 0x40012.l",)),
 (0x40018,"game_irq2_watchdog_trap","interrupt frame only","does not return","six-byte self-JMP trap; unexpected IRQ2 stops watchdog service","Verified",0x6,("jmp 0x40018.l",)),
 (0x4001E,"game_irq6_sound_veneer","interrupt frame only","no value; exits with RTE","tail-jumps through OS API 0x17E to the sound receive interrupt body","Verified",0x6,("jmp 0x17e.l",)),
 (0x40024,"game_exception_veneer","D0.w = exception action (OS supplies zero)","does not return","six-byte OS exception hook; tail-jumps to game_exception_abort","Verified",0x6,("jmp 0x40140.l",)),
 (0x40030,"game_playfield_init_veneer","void","void","six-byte OS hook; tail-jumps to game_playfield_init","Verified",0x6,("jmp 0x44a82.l",)),
 (0x40048,"game_options_veneer","void","void","six-byte OS game-options hook; tail-jumps to game_options_display","Verified",0x6,("jmp 0x5317c.l",)),
 (0x40054,"game_eeprom_config_veneer","void","D0.l = packed verification/config result","six-byte OS EEPROM-config hook; tail-jumps to slapstic_verify","Verified",0x6,("jmp 0x56eaa.l",)),
 (0x400DE,"scroll_to_slot_veneer","uint16 packed_slot","void","six-byte tail veneer to scroll_to_slot; preserves the target's normal stack ABI","Verified",0x6,("jmp 0x46c5e.l",)),
 (0x400E4,"init_display_veneer","uint16 main_palette_index, uint16 special_palette_variant","void","six-byte tail veneer to init_display; preserves the target's normal stack ABI","Verified",0x6,("jmp 0x43486.l",)),
 (0x400EA,"maze_setup_veneer","const uint8_t *maze_record","void","six-byte tail veneer to maze_setupnew; preserves the target's normal stack ABI","Verified",0x6,("jmp 0x44ac2.l",)),
 (0x400F0,"pf_replace_veneer","uint16 packed_maze_slot, uint16 new_object_type","void","six-byte tail veneer to pf_replace; preserves the target's normal stack ABI","Verified",0x6,("jmp 0x5f31e.l",)),
 (0x400F6,"mob_clear_veneer","uint16 mob_slot","void","six-byte tail veneer to moblist_remove_and_clear; preserves the target's normal stack ABI","Verified",0x6,("jmp 0x5ddda.l",)),
 (0x40140,"game_exception_abort","D0.w = exception action (OS supplies zero)","does not return","register-controlled exception entry: zero jumps to the watchdog-abort address; nonzero falls through to game_start","Verified",0xC,("cmpi.w 0x0, d0","bne.b 0x4014c","jmp 0x10000.l")),
 (0x4014C,"game_start","void","does not return","OS reset entry through JMP veneer 0x40000; initializes palette/profile pointers, sets SR=0x2300, and tail-jumps to m2mainloop","Verified",0x32,("move.l 0x910520, 0x904036.l","move.l 0x571da, 0x904042.l","move.w 0x2300, sr","jmp 0x42a66.l")),
 (0x4017E,"game_vblank","interrupt frame only","no value; exits with RTE","68010 interrupt entry through veneer 0x40006; saves/restores D0-D1/A0-A2; may take the watchdog-abort path or jump through the reset vector instead of returning","Verified",0x322,("movem.l d0-d1/a0-a2, -(a7)","move.w d0, 0x803100.l","move.w d0, 0x803140.l","addq.w 0x1, 0x904002.l","bge.w 0x40146","bne.w 0x40146","jsr 0x184.w","movea.l 0x0.w, a7","movea.l 0x4.w, a0","jmp (a0)","movem.l (a7)+, d0-d1/a0-a2","rte")),
 (0x404A0,"palette_power_warrior","D0.w = cycle byte offset, A1 = source palette, A2 = destination palette","void","frameless pointer-table leaf; preserves registers","Verified",0xE,("move.w (a1, d0.w), 0xa(a2)","move.w 0x10(a1, d0.w), 0x18(a2)","rts")),
 (0x404AE,"palette_hurt_warrior","D0.w = cycle byte offset, A1 = source palette, A2 = destination palette","void","frameless pointer-table leaf; preserves registers","Verified",0xE,("move.w (a1, d0.w), 0xa(a2)","move.w 0x2(a1, d0.w), 0x18(a2)","rts")),
 (0x404BC,"palette_power_valkyrie","D0.w = cycle byte offset, A1 = source palette, A2 = destination palette","void","frameless pointer-table leaf; preserves registers","Verified",0x14,("move.w (a1, d0.w), 0xc(a2)","move.w 0x10(a1, d0.w), 0x10(a2)","move.w 0x20(a1, d0.w), 0x12(a2)","rts")),
 (0x404D0,"palette_hurt_valkyrie","D0.w = cycle byte offset, A1 = source palette, A2 = destination palette","void","frameless pointer-table leaf; preserves registers","Verified",0x14,("move.w (a1, d0.w), 0xc(a2)","move.w 0x2(a1, d0.w), 0x10(a2)","move.w 0x4(a1, d0.w), 0x12(a2)","rts")),
 (0x404E4,"palette_power_wizard","D0.w = cycle byte offset, A1 = source palette, A2 = destination palette","void","frameless pointer-table leaf; preserves registers","Verified",0x14,("move.w (a1, d0.w), 0xc(a2)","move.w 0x10(a1, d0.w), 0x10(a2)","move.w 0x20(a1, d0.w), 0x14(a2)","rts")),
 (0x404F8,"palette_hurt_wizard","D0.w = cycle byte offset, A1 = source palette, A2 = destination palette","void","frameless pointer-table leaf; preserves registers","Verified",0x14,("move.w (a1, d0.w), 0xc(a2)","move.w 0x2(a1, d0.w), 0x10(a2)","move.w 0x4(a1, d0.w), 0x14(a2)","rts")),
 (0x4050C,"palette_power_elf","D0.w = cycle byte offset, A1 = source palette, A2 = destination palette","void","frameless pointer-table leaf; preserves registers","Verified",0xE,("move.w (a1, d0.w), 0x16(a2)","move.w 0x10(a1, d0.w), 0x18(a2)","rts")),
 (0x4051A,"palette_hurt_elf","D0.w = cycle byte offset, A1 = source palette, A2 = destination palette","void","frameless pointer-table leaf; preserves registers","Verified",0xE,("move.w (a1, d0.w), 0x16(a2)","move.w 0x2(a1, d0.w), 0x18(a2)","rts")),
 (0x42A66,"m2mainloop","void","does not return","one-time init followed by infinite VBLANK-semaphore dispatch loop","Verified",0x104,("link.w a6, 0xfffc","jsr 0x4327a.l","tst.w (a2)","clr.w (a2)","jsr 0x42d0a.l","jsr 0x4ae20.l","bra.w 0x42a7e")),
 (0x42DC8,"sound_system_reset","void","void","normal stack; calls OS reset_sound_cpu(0,0), installs 180-frame grace, clears state/retries, and resets queue","Verified",0x2C,("clr.l -(a7)","jsr 0x254.l","move.w 0xb4, 0x9049ee.l","clr.w 0x9049f0.l","clr.w 0x9049f4.l","jsr 0x4adae.l","rts")),
 (0x4ADAE,"sound_queue_reset","void","void","frameless leaf; fills all eight slots with 0xFF and zeroes byte head/tail indices","Verified",0x28,("clr.w d1","move.b 0xff, (a0, d0.w)","cmpi.w 0x8, d1","clr.b d0","move.b d0, 0x904054.l","move.b d0, 0x904053.l","rts")),
 (0x4ADD6,"enqueue_sound","uint8 sound_id","void","normal-stack leaf; capacity is seven entries and a full queue silently drops the new byte","Verified",0x4A,("move.b 0xb(a7), d2","move.b (a1), d0","sub.l d1, d0","and.l d1, d0","cmp.l d0, d1","move.b d2, (a0, d0.w)","addq.l 0x1, d0","move.b d0, (a1)","rts")),
 (0x4D12E,"alpha_clear_rect","uint16 column, uint16 width, uint16 row, uint16 height","void","normal stack; exact dimensions in alpha words/rows, 64-word (0x80-byte) row stride; zero width or height writes nothing","Verified",0x76,("move.w 0xa(a6), d3","move.w 0xe(a6), d5","move.w 0x12(a6), d4","addi.l 0x905000, d1","clr.w (a0)+","moveq 0x40, d1","move.w 0x16(a6), d0","rts")),
 (0x5317C,"game_options_display","void","void","OS game-options hook; passes the ROM descriptor stream to display_attract_screen (API 0x248)","Verified",0x10,("pea.l 0x5318c.l","jsr 0x248.l","addq.l 0x4, a7","rts")),
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
 if result.returncode or re.search(r"(?im)^(?:ERROR|FATAL)",result.stderr): raise SystemExit(f"radare2 orchestration audit failed at 0x{address:X}:\n{result.stderr}")
 return [item["opcode"] for item in json.loads(result.stdout)]

def runtime_check(root):
 loader=root/"doc"/"gauntlet_loader.r2"
 for address,name,_,_,_,_,size,required in CONTRACTS:
  operations=opcodes(root,loader,address,size)
  for expected in required:
   if expected not in operations: raise SystemExit(f"{name} (0x{address:X}): required instruction absent: {expected}")
 print(f"orchestration/sound contracts: analyzed {len(CONTRACTS)} entries; ABI evidence matches")

def main():
 parser=argparse.ArgumentParser(); parser.add_argument("--check",action="store_true"); parser.add_argument("--run-check",action="store_true"); args=parser.parse_args()
 here=Path(__file__).resolve().parent; root=here.parent; rom=(root/"row76.bin").read_bytes()
 if len(rom)!=0x20000 or hashlib.sha1(rom).hexdigest()!=ROM_SHA1: raise SystemExit("row76.bin is not the documented 128 KiB target ROM")
 sites=direct_sites(rom)
 rows=[{"address":f"0x{a:05X}","name":n,"arguments":arguments,"return":ret,"exceptional_convention":exception,"direct_control_sites":";".join(f"0x{x:05X}" for x in sites[a]),"confidence":confidence} for a,n,arguments,ret,exception,confidence,_,_ in CONTRACTS]
 output=here/"orchestration_sound_contracts.csv"
 if args.check:
  with output.open(newline="") as handle: old=list(csv.DictReader(handle))
  if old!=rows: raise SystemExit("orchestration_sound_contracts.csv is stale; regenerate it")
  print(f"orchestration_sound_contracts.csv: verified {len(rows)} entries")
 else:
  with output.open("w",newline="") as handle: writer=csv.DictWriter(handle,fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)
  print(f"wrote {len(rows)} rows to {output}")
 if args.run_check: runtime_check(root)

if __name__=="__main__": main()
