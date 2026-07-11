# Gauntlet II RE — Known Issues and Remaining Unknowns

No genuinely unresolved issue remains in the current audit.

The nonstandard callable-entry sweep is recorded in `07_function_index.md`, including direct, tail/shared-body, leaf/BSR-only, and register-indirect cases. The ROM/RAM boundary and indexed-base reconciliation is recorded in `05_data_reference.md` §5.0. The two formerly orphaned ROM blocks are classified there as runtime-dead residue, with their exact ranges and negative-reference evidence preserved rather than speculative table names.

Add a new item here only when code usage establishes a concrete contradiction or leaves a genuinely unresolved consumer, boundary, format, or callable target. Broad reminders to “audit everything” do not belong in this file once their coverage pass is complete.
