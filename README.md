# [Sega Saturn](https://en.wikipedia.org/wiki/Sega_Saturn) for MiSTer

## Hardware Requirements

- 128 MB SDRAM Module (Primary)
- SDRAM Module of any size (32MB-128MB) (Secondary)

> **Note:** Dual SDRAM modules is recommended for better compatibility.

## Status

Current status is WIP/Beta

Known issues:

## Experimental Cheat-Support POC

This branch includes an experimental Saturn cheat-support proof of concept for
testing. Treat the public/testing build from this branch as a Single-RAM
cheat-support POC unless a specific build is explicitly documented otherwise.
It is not a stock-core replacement yet.

The goal is for the POC to behave like the working Single-RAM all-cheats test
build: load the game normally, confirm it runs with cheats off, then enable one
cheat at a time from the OSD. Do not assume that every cheat works. Some cheat
files are game-version-specific, region-specific, or simply bad, and those may
still fail even if the core-side cheat logic is working.

Dual-RAM cheat support is still experimental and unresolved. A Dual-RAM crash,
freeze, or non-working cheat should not be used as proof that a cheat pack is
bad, and Dual-RAM behavior should not be treated as confirmed unless the exact
build has been hardware-tested and documented.

When reporting results, please include:

- Game name.
- Region/version, if known.
- Core/RBF filename used.
- Cheat file/name used.
- Whether the game boots with cheats off.
- What happens when enabling the cheat: works, does nothing, freezes, or
  crashes.

