# CPS3 Beta Audit Tool

`scripts/cps3_beta_audit.py` audits MiSTer CPS3 beta release files on Windows without extracting or inspecting copyrighted ROM archives.

## Usage

```powershell
python scripts/cps3_beta_audit.py "C:\MiSTer beta files\jtfriday_260612_mister.zip" "C:\MiSTer beta files\jtbeta.zip"
```

The MiSTer SD card root is optional. When it is omitted, the tool audits only the release ZIP and beta key ZIP.

With a MiSTer SD card mounted:

```powershell
python scripts/cps3_beta_audit.py "C:\MiSTer beta files\jtfriday_260612_mister.zip" "C:\MiSTer beta files\jtbeta.zip" "E:\"
```

With the expected `beta.bin` CRC32:

```powershell
python scripts/cps3_beta_audit.py "C:\MiSTer beta files\jtfriday_260612_mister.zip" "C:\MiSTer beta files\jtbeta.zip" "E:\" --expected-beta-crc 8b6976d8
```

Strict comparison against a dated reference package:

```powershell
python scripts/cps3_beta_audit.py "C:\MiSTer beta files\jtfriday_260612_mister.zip" "C:\MiSTer beta files\jtbeta.zip" "E:\" --expected-beta-crc 8b6976d8 --reference-label "Patreon 2026-06-12"
```

Comparison when the MiSTer SD card may already have a newer installed RBF:

```powershell
python scripts/cps3_beta_audit.py "C:\MiSTer beta files\jtfriday_260612_mister.zip" "C:\MiSTer beta files\jtbeta.zip" "E:\" --expected-beta-crc 8b6976d8 --reference-label "Patreon 2026-06-12" --allow-rbf-drift
```

Targeted comparison against the MiSTer SMB share:

```powershell
python scripts/cps3_beta_audit.py "C:\Users\djjoh\Downloads\jtfriday_260612_mister.zip" "C:\Users\djjoh\Downloads\jtbeta.zip" "\\MiSTer\sdcard" --expected-beta-crc 8b6976d8 --reference-label "Patreon 2026-06-12" --allow-rbf-drift --targeted-sd-copy
```

One-command helper with the default Patreon ZIPs and `\\MiSTer\sdcard`:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\run_cps3_beta_audit.ps1
```

Override the inputs when needed:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\run_cps3_beta_audit.ps1 -ReleaseZip "D:\Downloads\jtfriday_260612_mister.zip" -BetaZip "D:\Downloads\jtbeta.zip" -SdRoot "\\MiSTer\sdcard"
```

By default, the tool writes:

- `<patreon_zip_stem>_cps3_audit.md`
- `<patreon_zip_stem>_cps3_manifest.json`

Use `--out-dir`, `--report`, or `--manifest` to choose output paths.

The script also prints the generated Markdown and JSON paths at the end of each run.

## What It Checks

- Lists CPS3-related files in the Patreon ZIP.
- Validates `jtbeta.zip` and confirms it contains `beta.bin`.
- Verifies `beta.bin` against the ZIP-stored CRC, and against `--expected-beta-crc` when provided.
- Hashes `jtcps3.rbf` and CPS3 MRA files with CRC32 and SHA256.
- Parses CPS3 MRAs as XML and reports core name, setname, year, manufacturer, referenced ROM ZIP names, NVRAM entries, and button mappings.
- Compares release ZIP files against the MiSTer SD card when an SD root is provided.
- Flags missing, stale, mismatched, invalid, unparsable, or RBF version-drift files.

## Targeted SMB Audits

Direct recursive scans of `\\MiSTer\sdcard` can be slow because the SD card has many folders and SMB traversal adds latency. Use `--targeted-sd-copy` when auditing a network share. In this mode, the tool reads the reference ZIP first, determines the expected CPS3 install targets, copies only those files into a temporary MiSTer-shaped mirror, and compares against that mirror.

The targeted mirror is read-only with respect to the SD card: it copies from the SD card and never writes back to it. It only mirrors CPS3 install files such as `_Arcade/cores/jtcps3.rbf` and CPS3 MRAs under `_Arcade/`. It does not copy, extract, hash, validate, or inspect ROM ZIP contents.

`scripts\run_cps3_beta_audit.ps1` uses targeted SMB mode by default. It reads from the MiSTer SD card, copies only the expected CPS3 install files into a temporary local mirror, and exits with the Python audit tool's exit code.

## RBF Version Drift

`jtcps3.rbf` can differ from an older Patreon ZIP when the MiSTer SD card has already been updated. By default, an RBF content mismatch is still an error in strict comparison mode, but the report uses a safer message:

> Installed RBF differs from the reference package. This may be expected if the MiSTer SD card has a newer update. Do not overwrite without confirming which build is newer.

Use `--allow-rbf-drift` when comparing an updated MiSTer SD card against an older reference ZIP. Missing files, beta CRC mismatches, and MRA content mismatches are still errors.

Only use `--recommend-rbf-replace` after confirming the reference package is newer than the installed RBF. Do not overwrite a newer installed RBF with an older Patreon ZIP.

## ROM Boundary

The audit reports ROM ZIP names referenced by MRA metadata only. It does not extract, hash, validate, or inspect ROM archive contents.
