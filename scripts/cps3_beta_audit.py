#!/usr/bin/env python3
"""Audit MiSTer CPS3 beta release files without touching copyrighted ROMs."""

from __future__ import annotations

import argparse
import binascii
import datetime as dt
import hashlib
import json
import re
import shutil
import sys
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any, Iterable
from xml.etree import ElementTree as ET


REPORT_VERSION = 1
ROM_EXTENSIONS = {".zip", ".7z", ".rar"}
HASH_EXTENSIONS = {".mra", ".rbf"}
CRC_RE = re.compile(r"^(?:0x)?([0-9a-fA-F]{8})$")


@dataclass
class Issue:
    severity: str
    code: str
    message: str
    path: str | None = None


@dataclass
class FileHash:
    path: str
    source: str
    size: int
    crc32: str
    sha256: str
    modified: str | None = None


@dataclass
class MraInfo:
    path: str
    source: str
    parse_ok: bool
    core_name: str | None = None
    setname: str | None = None
    year: str | None = None
    manufacturer: str | None = None
    zip_names: list[str] = field(default_factory=list)
    nvram: list[dict[str, Any]] = field(default_factory=list)
    button_mappings: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None


def posix_path(name: str) -> str:
    return str(PurePosixPath(name.replace("\\", "/")))


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def parse_expected_crc(value: str | None) -> str | None:
    if not value:
        return None
    match = CRC_RE.match(value.strip())
    if not match:
        raise argparse.ArgumentTypeError("CRC must be 8 hex digits, optionally prefixed with 0x")
    return match.group(1).lower()


def crc32_hex(data: bytes) -> str:
    return f"{binascii.crc32(data) & 0xFFFFFFFF:08x}"


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def normalize_text(value: str | None) -> str | None:
    if value is None:
        return None
    text = " ".join(value.split())
    return text or None


def local_name(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[1].lower()
    return tag.lower()


def first_text(root: ET.Element, names: Iterable[str]) -> str | None:
    wanted = {name.lower() for name in names}
    for elem in root.iter():
        if local_name(elem.tag) in wanted:
            text = normalize_text(elem.text)
            if text:
                return text
    return None


def split_zip_names(value: str | None) -> list[str]:
    if not value:
        return []
    names: list[str] = []
    for piece in re.split(r"[|,;\s]+", value.strip()):
        piece = piece.strip().strip("\"'")
        if piece.lower().endswith(".zip") and piece not in names:
            names.append(piece)
    return names


def extract_zip_names(root: ET.Element) -> list[str]:
    names: list[str] = []
    for elem in root.iter():
        tag = local_name(elem.tag)
        if tag == "zip":
            for name in split_zip_names(elem.text):
                if name not in names:
                    names.append(name)
        for key, value in elem.attrib.items():
            if key.lower() == "zip" or value.lower().endswith(".zip") or ".zip" in value.lower():
                for name in split_zip_names(value):
                    if name not in names:
                        names.append(name)
    return names


def extract_nvram(root: ET.Element) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for elem in root.iter():
        tag = local_name(elem.tag)
        if "nvram" in tag:
            entry: dict[str, Any] = {"tag": tag}
            if elem.attrib:
                entry["attributes"] = dict(elem.attrib)
            text = normalize_text(elem.text)
            if text:
                entry["text"] = text
            entries.append(entry)
    return entries


def extract_buttons(root: ET.Element) -> list[dict[str, Any]]:
    mappings: list[dict[str, Any]] = []
    button_tags = {"buttons", "button", "joystick"}
    interesting_attrs = {"names", "default", "map", "player", "name", "input", "index"}
    for elem in root.iter():
        tag = local_name(elem.tag)
        if tag in button_tags or any(key.lower() in interesting_attrs for key in elem.attrib):
            if tag in button_tags:
                entry: dict[str, Any] = {"tag": tag}
                if elem.attrib:
                    entry["attributes"] = dict(elem.attrib)
                text = normalize_text(elem.text)
                if text:
                    entry["text"] = text
                mappings.append(entry)
    return mappings


def parse_mra_bytes(path: str, source: str, data: bytes) -> MraInfo:
    try:
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        return MraInfo(path=path, source=source, parse_ok=False, error=str(exc))

    core_name = first_text(root, ("rbf", "core", "core_name"))
    return MraInfo(
        path=path,
        source=source,
        parse_ok=True,
        core_name=core_name,
        setname=first_text(root, ("setname",)),
        year=first_text(root, ("year",)),
        manufacturer=first_text(root, ("manufacturer",)),
        zip_names=extract_zip_names(root),
        nvram=extract_nvram(root),
        button_mappings=extract_buttons(root),
    )


def is_rom_archive(path: str) -> bool:
    return PurePosixPath(path).suffix.lower() in ROM_EXTENSIONS


def is_hash_target(path: str) -> bool:
    p = PurePosixPath(path)
    lower_name = p.name.lower()
    return lower_name == "jtcps3.rbf" or (p.suffix.lower() == ".mra" and "cps3" in path.lower())


def file_hash(path: str, source: str, data: bytes, modified: str | None = None) -> FileHash:
    return FileHash(
        path=path,
        source=source,
        size=len(data),
        crc32=crc32_hex(data),
        sha256=sha256_hex(data),
        modified=modified,
    )


def zip_entry_modified(info: zipfile.ZipInfo) -> str:
    naive = dt.datetime(*info.date_time)
    return naive.isoformat()


def read_zip_entry(zf: zipfile.ZipFile, info: zipfile.ZipInfo) -> bytes:
    with zf.open(info, "r") as handle:
        return handle.read()


def classify_zip_entries(zip_path: Path) -> tuple[list[str], list[FileHash], list[MraInfo], list[Issue]]:
    cps3_related: list[str] = []
    hashes: list[FileHash] = []
    mras: list[MraInfo] = []
    issues: list[Issue] = []

    with zipfile.ZipFile(zip_path, "r") as zf:
        infos = [info for info in zf.infolist() if not info.is_dir()]
        parsed_mra_paths: set[str] = set()

        for info in infos:
            path = posix_path(info.filename)
            lower = path.lower()
            suffix = PurePosixPath(path).suffix.lower()
            name = PurePosixPath(path).name.lower()
            path_looks_cps3 = "cps3" in lower or name == "jtcps3.rbf"

            if path_looks_cps3:
                cps3_related.append(path)

            if name == "jtcps3.rbf":
                data = read_zip_entry(zf, info)
                hashes.append(file_hash(path, "patreon_zip", data, zip_entry_modified(info)))

            if suffix == ".mra":
                data = read_zip_entry(zf, info)
                mra = parse_mra_bytes(path, "patreon_zip", data)
                parsed_mra_paths.add(path)
                is_cps3_mra = path_looks_cps3 or (
                    mra.parse_ok
                    and (
                        (mra.core_name and "cps3" in mra.core_name.lower())
                        or any("cps3" in name.lower() for name in mra.zip_names)
                    )
                )
                if is_cps3_mra:
                    if path not in cps3_related:
                        cps3_related.append(path)
                    hashes.append(file_hash(path, "patreon_zip", data, zip_entry_modified(info)))
                    mras.append(mra)
                elif not mra.parse_ok and "cps3" in lower:
                    issues.append(Issue("error", "mra_parse_failed", mra.error or "MRA parse failed", path))

        for info in infos:
            path = posix_path(info.filename)
            if PurePosixPath(path).suffix.lower() == ".mra" and "cps3" in path.lower() and path not in parsed_mra_paths:
                issues.append(Issue("warning", "mra_not_parsed", "CPS3-looking MRA was not parsed", path))

    return sorted(cps3_related), hashes, mras, issues


def validate_beta_zip(beta_zip_path: Path, expected_crc: str | None) -> tuple[dict[str, Any], list[Issue]]:
    issues: list[Issue] = []
    result: dict[str, Any] = {
        "path": str(beta_zip_path),
        "contains_beta_bin": False,
        "zip_test_ok": False,
        "expected_crc32": expected_crc,
    }

    try:
        with zipfile.ZipFile(beta_zip_path, "r") as zf:
            bad_file = zf.testzip()
            result["zip_test_ok"] = bad_file is None
            if bad_file:
                issues.append(Issue("error", "beta_zip_crc_failed", f"ZIP CRC check failed at {bad_file}", bad_file))

            beta_infos = [
                info for info in zf.infolist()
                if not info.is_dir() and PurePosixPath(posix_path(info.filename)).name.lower() == "beta.bin"
            ]
            if not beta_infos:
                issues.append(Issue("error", "beta_bin_missing", "jtbeta.zip does not contain beta.bin"))
                return result, issues
            if len(beta_infos) > 1:
                issues.append(Issue("warning", "multiple_beta_bin", "jtbeta.zip contains multiple beta.bin entries"))

            info = beta_infos[0]
            data = read_zip_entry(zf, info)
            stored_crc = f"{info.CRC:08x}"
            computed_crc = crc32_hex(data)
            result.update(
                {
                    "contains_beta_bin": True,
                    "beta_bin_path": posix_path(info.filename),
                    "size": len(data),
                    "stored_crc32": stored_crc,
                    "computed_crc32": computed_crc,
                    "sha256": sha256_hex(data),
                    "stored_crc_matches_content": stored_crc == computed_crc,
                }
            )
            if stored_crc != computed_crc:
                issues.append(Issue("error", "beta_crc_mismatch", "beta.bin does not match ZIP stored CRC", posix_path(info.filename)))
            if expected_crc and computed_crc != expected_crc:
                issues.append(
                    Issue(
                        "error",
                        "beta_expected_crc_mismatch",
                        f"beta.bin CRC {computed_crc} does not match expected {expected_crc}",
                        posix_path(info.filename),
                    )
                )
    except zipfile.BadZipFile as exc:
        issues.append(Issue("error", "beta_zip_invalid", f"Invalid beta ZIP: {exc}"))

    return result, issues


def walk_sd_candidates(sd_root: Path) -> list[Path]:
    candidates: list[Path] = []
    for path in sd_root.rglob("*"):
        if not path.is_file():
            continue
        lower = path.name.lower()
        if lower == "jtcps3.rbf" or (path.suffix.lower() == ".mra" and "cps3" in str(path).lower()):
            candidates.append(path)
    return candidates


def rel_posix(path: Path, root: Path) -> str:
    return posix_path(str(path.relative_to(root)))


def sd_hashes_and_mras(sd_root: Path) -> tuple[list[FileHash], list[MraInfo], list[Issue]]:
    hashes: list[FileHash] = []
    mras: list[MraInfo] = []
    issues: list[Issue] = []
    for path in walk_sd_candidates(sd_root):
        rel = rel_posix(path, sd_root)
        try:
            data = path.read_bytes()
        except OSError as exc:
            issues.append(Issue("error", "sd_read_failed", str(exc), rel))
            continue

        try:
            modified = dt.datetime.fromtimestamp(path.stat().st_mtime, dt.timezone.utc).replace(microsecond=0).isoformat()
        except OSError:
            modified = None
        hashes.append(file_hash(rel, "sd_card", data, modified))
        if path.suffix.lower() == ".mra":
            mra = parse_mra_bytes(rel, "sd_card", data)
            mras.append(mra)
            if not mra.parse_ok:
                issues.append(Issue("error", "sd_mra_parse_failed", mra.error or "MRA parse failed", rel))
    return hashes, mras, issues


def copy_targeted_sd_files(sd_root: Path, targets: list[FileHash]) -> tuple[Path, dict[str, Any], list[Issue]]:
    mirror = Path(tempfile.mkdtemp(prefix="cps3_audit_sd_mirror_"))
    info: dict[str, Any] = {
        "enabled": True,
        "source_root": str(sd_root),
        "mirror_root": str(mirror),
        "copied": [],
        "missing": [],
        "failed": [],
    }
    issues: list[Issue] = []

    for target in targets:
        rel = posix_path(target.path)
        if is_rom_archive(rel):
            continue
        parts = PurePosixPath(rel).parts
        src = sd_root.joinpath(*parts)
        dst = mirror.joinpath(*parts)
        if not src.is_file():
            info["missing"].append(rel)
            continue
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            info["copied"].append(rel)
        except OSError as exc:
            info["failed"].append({"path": rel, "error": str(exc)})
            issues.append(Issue("error", "sd_target_copy_failed", f"Could not copy targeted SD file: {exc}", rel))

    return mirror, info, issues


def find_sd_match(zip_path: str, sd_by_rel: dict[str, FileHash], sd_by_name: dict[str, list[FileHash]]) -> FileHash | None:
    normalized = posix_path(zip_path).lower()
    if normalized in sd_by_rel:
        return sd_by_rel[normalized]
    base = PurePosixPath(normalized).name
    matches = sd_by_name.get(base, [])
    if len(matches) == 1:
        return matches[0]
    return None


def is_jtcps3_rbf(path: str) -> bool:
    return PurePosixPath(path).name.lower() == "jtcps3.rbf"


def compare_release_to_sd(
    zip_hashes: list[FileHash],
    sd_hashes: list[FileHash],
    allow_rbf_drift: bool,
    recommend_rbf_replace: bool,
) -> tuple[list[dict[str, Any]], list[Issue]]:
    issues: list[Issue] = []
    comparisons: list[dict[str, Any]] = []
    sd_by_rel = {item.path.lower(): item for item in sd_hashes}
    sd_by_name: dict[str, list[FileHash]] = {}
    for item in sd_hashes:
        sd_by_name.setdefault(PurePosixPath(item.path.lower()).name, []).append(item)

    matched_sd_paths: set[str] = set()
    for release in zip_hashes:
        sd_match = find_sd_match(release.path, sd_by_rel, sd_by_name)
        row: dict[str, Any] = {
            "release_path": release.path,
            "sd_path": sd_match.path if sd_match else None,
            "status": "missing_on_sd" if sd_match is None else "match",
        }
        if sd_match is None:
            issues.append(Issue("error", "missing_on_sd", "Release file was not found on the SD card", release.path))
        else:
            matched_sd_paths.add(sd_match.path.lower())
            row["release_sha256"] = release.sha256
            row["sd_sha256"] = sd_match.sha256
            row["release_size"] = release.size
            row["sd_size"] = sd_match.size
            if release.sha256 != sd_match.sha256:
                if is_jtcps3_rbf(release.path):
                    row["status"] = "rbf_version_drift"
                    row["message"] = (
                        "Installed RBF differs from the reference package. This may be expected if the MiSTer SD card has "
                        "a newer update. Do not overwrite without confirming which build is newer."
                    )
                    if recommend_rbf_replace:
                        row["recommendation"] = "User requested replacement guidance: replace only after confirming the reference package is newer."
                    severity = "warning" if allow_rbf_drift else "error"
                    issues.append(Issue(severity, "rbf_version_drift", row["message"], release.path))
                else:
                    row["status"] = "content_mismatch"
                    issues.append(Issue("error", "sd_file_mismatch", "SD card file does not match release ZIP", release.path))
            elif release.modified and sd_match.modified and sd_match.modified < release.modified:
                row["status"] = "match_but_older_timestamp"
                issues.append(Issue("warning", "sd_timestamp_older", "SD card timestamp is older than release ZIP timestamp", release.path))
        comparisons.append(row)

    release_names = {PurePosixPath(item.path.lower()).name for item in zip_hashes}
    for sd_item in sd_hashes:
        if sd_item.path.lower() in matched_sd_paths:
            continue
        if PurePosixPath(sd_item.path.lower()).name in release_names:
            continue
        comparisons.append({"release_path": None, "sd_path": sd_item.path, "status": "extra_or_stale_on_sd"})
        issues.append(Issue("warning", "extra_or_stale_on_sd", "CPS3-looking file exists on SD but not in release ZIP", sd_item.path))

    return comparisons, issues


def dataclass_list(items: Iterable[Any]) -> list[dict[str, Any]]:
    return [item.__dict__ for item in items]


def write_json(path: Path, manifest: dict[str, Any]) -> None:
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def markdown_table(headers: list[str], rows: Iterable[Iterable[Any]]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    for row in rows:
        values = []
        for value in row:
            text = "" if value is None else str(value)
            values.append(text.replace("|", "\\|").replace("\n", " "))
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines)


def write_markdown(path: Path, manifest: dict[str, Any]) -> None:
    issues = manifest["issues"]
    lines: list[str] = [
        "# MiSTer CPS3 Beta Audit",
        "",
        f"- Generated: `{manifest['generated_at']}`",
        f"- Patreon ZIP: `{manifest['inputs']['patreon_zip']}`",
        f"- beta key ZIP: `{manifest['inputs']['beta_zip']}`",
        f"- Reference label: `{manifest['inputs']['reference_label']}`",
    ]
    if manifest["inputs"].get("sd_root"):
        lines.append(f"- MiSTer SD root: `{manifest['inputs']['sd_root']}`")
    if manifest.get("sd_card", {}).get("targeted_copy", {}).get("enabled"):
        targeted = manifest["sd_card"]["targeted_copy"]
        lines.append(f"- Targeted SD mirror: `{targeted['mirror_root']}`")
    lines.extend(
        [
            f"- Overall status: **{manifest['status']}**",
            "",
            "## Issues",
            "",
        ]
    )
    if issues:
        lines.append(markdown_table(["Severity", "Code", "Path", "Message"], ((i["severity"], i["code"], i.get("path"), i["message"]) for i in issues)))
    else:
        lines.append("No issues found.")

    beta = manifest["beta_zip"]
    lines.extend(
        [
            "",
            "## beta.bin",
            "",
            markdown_table(
                ["Field", "Value"],
                (
                    ("Present", beta.get("contains_beta_bin")),
                    ("ZIP CRC test OK", beta.get("zip_test_ok")),
                    ("Path", beta.get("beta_bin_path")),
                    ("Size", beta.get("size")),
                    ("Stored CRC32", beta.get("stored_crc32")),
                    ("Computed CRC32", beta.get("computed_crc32")),
                    ("Expected CRC32", beta.get("expected_crc32")),
                    ("SHA256", beta.get("sha256")),
                ),
            ),
            "",
            "## CPS3 Files In Patreon ZIP",
            "",
        ]
    )
    cps3_files = manifest["patreon_zip"]["cps3_related_files"]
    if cps3_files:
        lines.extend(f"- `{name}`" for name in cps3_files)
    else:
        lines.append("No CPS3-related files found.")

    lines.extend(["", "## Hashes", ""])
    all_hashes = manifest["patreon_zip"]["hashes"] + manifest.get("sd_card", {}).get("hashes", [])
    if all_hashes:
        lines.append(markdown_table(["Source", "Path", "Size", "CRC32", "SHA256"], ((h["source"], h["path"], h["size"], h["crc32"], h["sha256"]) for h in all_hashes)))
    else:
        lines.append("No `jtcps3.rbf` or CPS3 MRA files were hashed.")

    lines.extend(["", "## MRA Metadata", ""])
    mras = manifest["patreon_zip"]["mras"] + manifest.get("sd_card", {}).get("mras", [])
    if mras:
        lines.append(
            markdown_table(
                ["Source", "Path", "Core", "Setname", "Year", "Manufacturer", "ZIP names", "NVRAM", "Buttons"],
                (
                    (
                        m["source"],
                        m["path"],
                        m.get("core_name"),
                        m.get("setname"),
                        m.get("year"),
                        m.get("manufacturer"),
                        ", ".join(m.get("zip_names", [])),
                        json.dumps(m.get("nvram", []), sort_keys=True),
                        json.dumps(m.get("button_mappings", []), sort_keys=True),
                    )
                    for m in mras
                ),
            )
        )
    else:
        lines.append("No CPS3 MRAs were parsed.")

    if manifest.get("sd_card"):
        lines.extend(["", "## SD Comparison", ""])
        targeted = manifest["sd_card"].get("targeted_copy")
        if targeted and targeted.get("enabled"):
            lines.extend(
                [
                    "",
                    "Targeted SD copy mode was used. Only CPS3 install target files from the reference package were copied into the temporary mirror for comparison.",
                    "",
                    markdown_table(
                        ["Source root", "Mirror root", "Copied", "Missing", "Failed"],
                        (
                            (
                                targeted.get("source_root"),
                                targeted.get("mirror_root"),
                                len(targeted.get("copied", [])),
                                len(targeted.get("missing", [])),
                                len(targeted.get("failed", [])),
                            ),
                        ),
                    ),
                    "",
                ]
            )
        lines.append(
            markdown_table(
                ["Status", "Release Path", "SD Path", "Message"],
                ((c["status"], c.get("release_path"), c.get("sd_path"), c.get("message")) for c in manifest["sd_card"]["comparisons"]),
            )
        )

    lines.extend(
        [
            "",
            "## RBF Drift",
            "",
            "If `jtcps3.rbf` differs, the installed RBF may be newer than the reference package. Do not overwrite it without confirming which build is newer.",
            "",
            "## ROM Handling",
            "",
            "This audit does not extract, hash, or validate copyrighted ROM archive contents. ROM ZIP names are reported only when referenced by MRA metadata.",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def build_manifest(args: argparse.Namespace) -> dict[str, Any]:
    issues: list[Issue] = []
    patreon_zip = Path(args.patreon_zip).expanduser().resolve()
    beta_zip = Path(args.beta_zip).expanduser().resolve()
    sd_root = Path(args.sd_root).expanduser().resolve() if args.sd_root else None

    for label, path in (("Patreon ZIP", patreon_zip), ("beta key ZIP", beta_zip)):
        if not path.is_file():
            issues.append(Issue("error", "input_missing", f"{label} does not exist or is not a file", str(path)))
    if sd_root and not sd_root.is_dir():
        issues.append(Issue("error", "sd_root_missing", "MiSTer SD root does not exist or is not a directory", str(sd_root)))

    if any(issue.severity == "error" and issue.code == "input_missing" for issue in issues):
        return {
            "report_version": REPORT_VERSION,
            "generated_at": now_iso(),
            "status": "error",
            "inputs": {
                "patreon_zip": str(patreon_zip),
                "beta_zip": str(beta_zip),
                "sd_root": str(sd_root) if sd_root else None,
                "reference_label": args.reference_label,
                "targeted_sd_copy": args.targeted_sd_copy,
            },
            "issues": dataclass_list(issues),
        }

    beta_result, beta_issues = validate_beta_zip(beta_zip, args.expected_beta_crc)
    issues.extend(beta_issues)

    cps3_files: list[str] = []
    zip_hashes: list[FileHash] = []
    zip_mras: list[MraInfo] = []
    try:
        cps3_files, zip_hashes, zip_mras, zip_issues = classify_zip_entries(patreon_zip)
        issues.extend(zip_issues)
    except zipfile.BadZipFile as exc:
        issues.append(Issue("error", "patreon_zip_invalid", f"Invalid Patreon ZIP: {exc}", str(patreon_zip)))

    if not any(PurePosixPath(item.path).name.lower() == "jtcps3.rbf" for item in zip_hashes):
        issues.append(Issue("error", "jtcps3_rbf_missing", "jtcps3.rbf was not found in the Patreon ZIP"))
    if not zip_mras:
        issues.append(Issue("warning", "cps3_mra_missing", "No CPS3 MRAs were found in the Patreon ZIP"))

    manifest: dict[str, Any] = {
        "report_version": REPORT_VERSION,
        "generated_at": now_iso(),
        "inputs": {
            "patreon_zip": str(patreon_zip),
            "beta_zip": str(beta_zip),
            "sd_root": str(sd_root) if sd_root else None,
            "reference_label": args.reference_label,
            "allow_rbf_drift": args.allow_rbf_drift,
            "recommend_rbf_replace": args.recommend_rbf_replace,
            "targeted_sd_copy": args.targeted_sd_copy,
        },
        "beta_zip": beta_result,
        "patreon_zip": {
            "cps3_related_files": cps3_files,
            "hashes": dataclass_list(zip_hashes),
            "mras": dataclass_list(zip_mras),
        },
    }

    if sd_root and sd_root.is_dir():
        compare_root = sd_root
        targeted_info: dict[str, Any] | None = None
        if args.targeted_sd_copy:
            compare_root, targeted_info, copy_issues = copy_targeted_sd_files(sd_root, zip_hashes)
            issues.extend(copy_issues)

        sd_hashes, sd_mras, sd_issues = sd_hashes_and_mras(compare_root)
        comparisons, compare_issues = compare_release_to_sd(
            zip_hashes,
            sd_hashes,
            args.allow_rbf_drift,
            args.recommend_rbf_replace,
        )
        issues.extend(sd_issues)
        issues.extend(compare_issues)
        manifest["sd_card"] = {
            "root": str(sd_root),
            "comparison_root": str(compare_root),
            "hashes": dataclass_list(sd_hashes),
            "mras": dataclass_list(sd_mras),
            "comparisons": comparisons,
        }
        if targeted_info:
            manifest["sd_card"]["targeted_copy"] = targeted_info

    if any(issue.severity == "error" for issue in issues):
        status = "error"
    elif any(issue.severity == "warning" for issue in issues):
        status = "warning"
    else:
        status = "ok"
    manifest["status"] = status
    manifest["issues"] = dataclass_list(issues)
    return manifest


def default_output_paths(patreon_zip: str, output_dir: str | None) -> tuple[Path, Path]:
    base_dir = Path(output_dir).expanduser().resolve() if output_dir else Path.cwd()
    stem = Path(patreon_zip).stem
    return base_dir / f"{stem}_cps3_audit.md", base_dir / f"{stem}_cps3_manifest.json"


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit MiSTer CPS3 beta files from a Patreon ZIP and jtbeta.zip without extracting ROMs.",
    )
    parser.add_argument("patreon_zip", help="Path to the Patreon release ZIP, for example jtfriday_260612_mister.zip")
    parser.add_argument("beta_zip", help="Path to jtbeta.zip")
    parser.add_argument("sd_root", nargs="?", help="Optional MiSTer SD card root path")
    parser.add_argument("--expected-beta-crc", type=parse_expected_crc, help="Optional expected CRC32 for beta.bin, as 8 hex digits")
    parser.add_argument("--reference-label", default="reference package", help="Human-readable label for the package being compared")
    parser.add_argument("--allow-rbf-drift", action="store_true", help="Treat jtcps3.rbf content drift as a warning instead of an error")
    parser.add_argument(
        "--targeted-sd-copy",
        action="store_true",
        help="Copy only expected CPS3 install files from sd_root to a temporary mirror instead of recursively scanning sd_root",
    )
    parser.add_argument(
        "--recommend-rbf-replace",
        action="store_true",
        help="Include replacement guidance for jtcps3.rbf drift after you have confirmed the reference is newer",
    )
    parser.add_argument("--out-dir", help="Directory for the Markdown report and JSON manifest")
    parser.add_argument("--report", help="Explicit Markdown report path")
    parser.add_argument("--manifest", help="Explicit JSON manifest path")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    default_report, default_manifest = default_output_paths(args.patreon_zip, args.out_dir)
    report_path = Path(args.report).expanduser().resolve() if args.report else default_report
    manifest_path = Path(args.manifest).expanduser().resolve() if args.manifest else default_manifest
    report_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)

    manifest = build_manifest(args)
    write_json(manifest_path, manifest)
    write_markdown(report_path, manifest)

    print(f"Report: {report_path}")
    print(f"Manifest: {manifest_path}")
    targeted = manifest.get("sd_card", {}).get("targeted_copy")
    if targeted and targeted.get("enabled"):
        print(f"Targeted SD mirror: {targeted['mirror_root']}")
    print(f"Status: {manifest['status']}")
    if manifest.get("issues"):
        print(f"Issues: {len(manifest['issues'])}")
    return 1 if manifest["status"] == "error" else 0


if __name__ == "__main__":
    raise SystemExit(main())
