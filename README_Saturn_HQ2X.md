# Saturn_HQ2X Experimental Dual-RAM HDMI Core

This is an experimental HQ2x visual test build, not a replacement for the normal MiSTer Saturn core.

## What This Core Is

`Saturn_HQ2X.rbf` is a special-purpose Saturn Dual-RAM build for MiSTer FPGA. It is HDMI-only, forces full HQ2x video processing on, and uses a stripped/maximized-for-fit configuration so the HQ2x path can fit in the FPGA.

This build is intended for users who specifically want to compare HQ2x visuals against the normal Saturn core. It is not intended to replace the stock Saturn Dual-RAM core for daily use.

## Comparison With Stock Saturn

| Feature | Stock Saturn Dual-RAM Core | Saturn_HQ2X |
| --- | --- | --- |
| Intended use | Normal/default Saturn core | Experimental HQ2x visual comparison |
| Compatibility focus | Best compatibility | Special-purpose test build |
| HQ2x | Not forced | Full HQ2x forced on |
| Video output | Normal MiSTer output options, depending on build | HDMI-only |
| Aspect/crop/scaler controls | Normal aspect, crop, and scaler controls | Aspect/crop helpers stripped |
| Direct Video/VGA/analog options | Available depending on build and setup | Removed/disabled |
| Cheats | Normal core behavior | Disabled |
| Correct 4:3 handling | Internal controls available | Requires display-side 4:3 correction |
| Recommended for daily play | Yes | No, unless you accept the limitations |

## Requirements

- MiSTer FPGA setup.
- Dual SDRAM installed.
- HDMI output.
- A TV, monitor, or scaler that can force 4:3 if you want correct aspect ratio.
- Normal Saturn BIOS and game setup required by the standard MiSTer Saturn core.

## Installation

Copy the RBF to the MiSTer console folder:

```text
_Console/Saturn_HQ2X.rbf
```

On MiSTer, select `Saturn_HQ2X` from the core list.

Keep the normal Saturn core installed. This build does not replace it.

## Recommended Display Setup

Internal 4:3/aspect metadata and helper logic were stripped to make the HQ2x build fit. If your display is left in a default 16:9 mode, the image may appear stretched.

Before judging the HQ2x image, set your TV, monitor, or external scaler to a non-stretched mode such as:

- 4:3
- Original
- Just Scan plus 4:3
- Screen Fit / non-stretched mode

The exact label depends on the display.

## Known Limitations

- The image will look widescreen or stretched if the display is left in 16:9.
- No internal 4:3/aspect fix is included.
- HDMI-only.
- Cheats are disabled.
- This is not the stock daily-use Saturn core.
- Some display convenience options are removed.
- Not tested across the full Saturn library.
- Timing and resource margin are very tight.
- Users should keep the normal Saturn core installed.

## Technical Notes

Full HQ2x did not fit in the normal full-feature Dual-RAM HDMI build. This RBF only fits after a max-strip configuration that removes optional video features and forces the HQ2x path.

The working HQ2x video path depends on reconnecting `VGA_DE` to the video mixer output and disabling ascal downscale. The confirmed working build uses 100% of available RAM blocks, so even small feature restores can affect timing.

Internal 4:3 restore attempts were tested but not included because they failed timing:

- `TEST1`, constant 4:3 metadata: hold slack `-0.434 ns`.
- `TEST2`, lightweight original aspect metadata: setup slack `-0.577 ns`, hold slack `-0.281 ns`.

Rejected timing-failed builds are not included in this package.

## Recommended Use

Use the stock Saturn Dual-RAM core for normal play.

Use `Saturn_HQ2X.rbf` only for HQ2x visual comparison/testing, and switch the TV/display/scaler to 4:3 before judging the result.

## File And Hash

RBF:

```text
Saturn_HQ2X.rbf
```

SHA256:

```text
249D818C4428E1AB25FB27155AA2C0FBD03BB35528E3808DC356B6ECC12CD5FB
```

## Disclaimer

This is an unofficial experimental build. It is not endorsed as a replacement for the official MiSTer Saturn core.
