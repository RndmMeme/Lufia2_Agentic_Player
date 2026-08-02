# Terrorwave table reference

Upstream: https://github.com/abyssonym/terrorwave/tree/master/tables

Imported commit: `71392f9553ba4657f5c6736644ad0cddea94c0ae`

The `tables/` directory is an unmodified snapshot of Abyssonym's table
definitions. It is used as a read-only schema reference for the Lufia II ROM
and WRAM mapping. In particular, `tables_list.frue.txt` supplies table
locations/counts while the `struct_*.txt` files describe their records.

## Trust policy

Abyssonym's explicit pointers, offsets, counts, field sizes, field names and
documented values are authoritative upstream facts for this project. They do
not require an additional live WRAM experiment before being added to the base
of truth.

Live Mesen experiments remain necessary only for information the upstream
tables do not specify, such as runtime WRAM locations, transient state and the
semantics of otherwise unnamed numeric mode values.

The player's randomized ROM is never modified by the extraction tools.
