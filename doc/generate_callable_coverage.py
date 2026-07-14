#!/usr/bin/env python3
"""Reconcile every documented game-ROM callable entry with checked catalogs."""

from __future__ import annotations
import argparse, csv, re
from pathlib import Path

ROW_RE=re.compile(r"^\|\s*(0x[0-9A-Fa-f]+)\s*\|\s*`([^`]+)`")

def main():
 parser=argparse.ArgumentParser(); parser.add_argument("--check",action="store_true"); args=parser.parse_args()
 here=Path(__file__).resolve().parent
 indexed={}
 for line in (here/"07_function_index.md").read_text().splitlines():
  match=ROW_RE.match(line)
  if not match: continue
  address=int(match.group(1),16)
  if 0x40000<=address<=0x5ffff: indexed.setdefault(address,match.group(2))
 coverage={address:set() for address in indexed}
 extras=[]
 for path in sorted(here.glob("*_contracts.csv")):
  # This artifact is intentionally the game-ROM union.  OS contract batches
  # have their own low-address union and must not be interpreted as missing
  # 0x40000-0x5FFFF game index rows.
  if path.name.startswith("os_"): continue
  with path.open(newline="") as handle:
   reader=csv.DictReader(handle)
   fields=reader.fieldnames or []
   key="address" if "address" in fields else "target" if "target" in fields else None
   if key is None: continue
   for row in reader:
    address=int(row[key],16)
    if address not in indexed: extras.append((path.name,address))
    else: coverage[address].add(path.name)
 missing=[address for address,names in coverage.items() if not names]
 if extras: raise SystemExit("contract addresses absent from index: "+", ".join(f"{name}:0x{address:X}" for name,address in extras))
 if missing: raise SystemExit("indexed entries without checked contract: "+", ".join(f"0x{address:X}" for address in missing))
 rows=[{"address":f"0x{address:05X}","name":indexed[address],"catalogs":";".join(sorted(coverage[address])),"confidence":"Verified"} for address in sorted(indexed)]
 output=here/"callable_contract_coverage.csv"
 if args.check:
  with output.open(newline="") as handle: old=list(csv.DictReader(handle))
  if old!=rows: raise SystemExit("callable_contract_coverage.csv is stale; regenerate it")
  print(f"callable contract coverage: verified {len(rows)}/{len(indexed)} indexed game entries")
 else:
  with output.open("w",newline="") as handle: writer=csv.DictWriter(handle,fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)
  print(f"wrote {len(rows)} covered entries to {output}")

if __name__=="__main__": main()
