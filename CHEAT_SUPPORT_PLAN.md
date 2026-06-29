# Saturn MiSTer Cheat Support Plan

## Tester Scope for This Branch

This branch should be treated as an experimental Saturn cheat-support proof of
concept. The public/testing target is the Single-RAM cheat-support POC unless a
specific RBF is explicitly documented otherwise. It is intended to behave like
the working Single-RAM all-cheats build, but it is not a stock-core replacement
yet and it does not guarantee that every cheat will work.

For testing, first boot the game with cheats off and confirm normal game
behavior. Then enable one cheat at a time from the OSD and record the result.
Some cheat files are tied to a specific game version, region, or memory layout;
a bad or mismatched cheat file may still do nothing, freeze, or crash even when
the core-side cheat path is functioning.

Please report:

- Game name.
- Region/version, if known.
- Core/RBF filename used.
- Cheat file/name used.
- Whether the game boots with cheats off.
- Whether enabling the cheat works, does nothing, freezes, or crashes.

Dual-RAM cheat support is not confirmed by this POC. Dual-RAM cheat activation
has unresolved hardware behavior and should not be used as proof that a cheat
file or cheat pack is correct or incorrect unless the exact Dual-RAM build has
been separately hardware-confirmed and documented.

## 1. MiSTer Cheat Input Path

MiSTer cheat files are delivered to a core through the existing `hps_io`
download interface. The Saturn wrapper already exposes that interface in
`Saturn.sv`:

- `ioctl_download` indicates an active transfer.
- `ioctl_index` identifies the transfer type.
- `ioctl_addr` is the byte offset within the transferred data.
- `ioctl_data` carries the downloaded data.
- `ioctl_wr` marks a valid write beat.

Other MiSTer console cores declare a cheat-related OSD entry in `CONF_STR` and
receive cheat data through the same download path. Cheat records commonly
contain flags, an address, an optional compare value, and a replacement value.

The POC uses the existing path in `Saturn.sv` to receive cheat data without
changing `sys/hps_io.sv`.

## 2. Likely Saturn Memory Hook Points

The preferred integration point is the root `Saturn.sv` wrapper, where Saturn
memory buses are connected to their storage backends.

Primary CPU-visible targets:

- High work RAM (`RAMH`): `ramh_din`, `ramh_wr`, and the `MEM_DI` read mux.
- Low work RAM (`RAML`): `raml_din`, `raml_wr`, and the `MEM_DI` read mux.
- Backup SRAM: potentially useful later, but not required for the first proof
  of concept.

High work RAM needs particular care because it has two backends:

- Single-SDRAM builds route it through `rtl/ddram.sv`.
- Dual-SDRAM builds route it through `rtl/sdram2.sv`.

The root wrapper sees both configurations, but only the Single-RAM POC behavior
should be treated as the current working tester reference. Dual-RAM behavior is
still experimental and unresolved unless a specific build has been separately
verified.

Additional memory regions can be considered after the work-RAM path is proven:

- Cartridge DRAM and backup cartridge RAM
- CD RAM
- VDP1 VRAM
- ST-V-specific cartridge and RAX memory

These are not Stage 1 targets.

## 3. SH-2 Cache Risks

Both Saturn SH-2 CPUs instantiate `SH7604_CACHE` through
`rtl/SH/SH7604/SH7604.sv`. A cheat write performed only in external RAM is not
guaranteed to become immediately visible to code reading a cached line.

Important consequences:

- Direct DDR3 or SDRAM patching can leave stale values in either SH-2 cache.
- Periodic freeze writes alone may not be sufficient for cached variables.
- Read replacement at the external memory mux only affects cache misses and
  uncached reads.
- A complete design may need cache-aware replacement, invalidation, or an
  explicit purge path for both SH-2 instances.

Stage 1 should avoid claiming general cheat compatibility. Hardware testing can
confirm specific game/cheat combinations, but it should not be read as a
guarantee that all Saturn cheats work.

## 4. Staged Implementation Plan

### Stage 1: Input and Minimal Work-RAM Proof of Concept

- Add a cheat-related OSD entry to the Saturn `CONF_STR`.
- Decode cheat downloads through the MiSTer ioctl path.
- Load a small fixed number of address/value records.
- Support a deliberately narrow work-RAM replacement path.
- Validate one known cheat against a real game on hardware.
- Document whether the tested variable is cached and whether read replacement,
  write clamping, or repeated writes are required.

### Stage 2: Cache-Aware Behavior

- Define a shared cheat lookup interface for both SH-2 instances.
- Add cache-aware read replacement or targeted invalidation.
- Confirm behavior for cached and uncached aliases.
- Test compare-before-replace semantics.

### Stage 3: Freeze Writes

- Add a periodic writer for cheats that must continually restore values.
- Arbitrate writes correctly for both `rtl/ddram.sv` and `rtl/sdram2.sv`
  backends.
- Preserve normal CPU, DMA, and video memory traffic.

### Stage 4: Broader Coverage and Cleanup

- Add optional coverage for cartridge RAM, backup SRAM, CD RAM, or ST-V memory
  only where real cheats require it.
- Add record limits, reset behavior, and status reporting.
- Test both single-SDRAM and dual-SDRAM builds, documenting them separately.

## 5. Stage 1 Proof-of-Concept Goal

The Stage 1 goal is to prove end-to-end delivery and enforcement of one simple
Saturn work-RAM cheat without changing SH-2 cache internals yet:

1. MiSTer loads one cheat record through the standard ioctl cheat download.
2. The root `Saturn.sv` wrapper stores the record.
3. The wrapper applies the replacement to a selected high- or low-work-RAM
   access.
4. A real game visibly reflects the changed value.
5. The test records whether cache effects limit reliability.

Success means the input format, address mapping, and minimal Single-RAM hook are
correct for the tested game/cheat combination. It does not mean that arbitrary
Saturn cheats are supported, and it does not confirm Dual-RAM cheat behavior.
