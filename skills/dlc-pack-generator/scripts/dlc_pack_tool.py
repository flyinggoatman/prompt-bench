#!/usr/bin/env python3
"""Build and validate Prompt Bench DLC bundles using only the Python stdlib."""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

MAX_UPLOAD = 512 * 1024
KNOWN_KEYS = {
    "pack", "private", "shared", "masters", "people",
    "categories", "dials", "variation", "fields",
}
MASTER_CANDIDATES = "EFGHIJKLMNOPQRSTUVWXYZ0123456789"


class PackError(Exception):
    pass


def fail(message: str) -> None:
    raise PackError(message)


def repo_root_from_script() -> Path:
    return Path(__file__).resolve().parents[3]


def load_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        fail(f"not found: {path}")
    except json.JSONDecodeError as exc:
        fail(f"{path}: invalid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}")


def dump_bytes(obj) -> bytes:
    return (json.dumps(obj, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def write_json(path: Path, obj) -> None:
    data = dump_bytes(obj)
    if len(data) > MAX_UPLOAD:
        fail(f"{path.name}: {len(data)} bytes exceeds Prompt Bench's 512 KB upload limit")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    if not slug:
        fail("theme/slug must contain at least one letter or digit")
    return slug


def scan_master_ids(repo_root: Path) -> set[str]:
    ids: set[str] = set()
    packs = repo_root / "packs"
    if not packs.is_dir():
        return ids
    for path in packs.rglob("*.json"):
        try:
            obj = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(obj, dict):
            continue
        for master in obj.get("masters", []) or []:
            if isinstance(master, dict) and isinstance(master.get("id"), str):
                ids.add(master["id"])
    return ids


def choose_master_id(repo_root: Path) -> str:
    used = scan_master_ids(repo_root)
    for candidate in MASTER_CANDIDATES:
        if candidate not in used:
            return candidate
    fail("no free single-character master ID remains; specify one explicitly after reviewing collisions")


def normalize_item(item, default_m: str, label: str, index: int) -> dict:
    if isinstance(item, str):
        text = item.strip()
        masters = default_m
    elif isinstance(item, dict):
        text = item.get("t", "")
        masters = item.get("m", default_m)
        if not isinstance(text, str):
            fail(f"{label} item {index}: t must be a string")
        text = text.strip()
    else:
        fail(f"{label} item {index}: expected a string or {{m,t}} object")
    if not text:
        fail(f"{label} item {index}: text is empty")
    if not isinstance(masters, str) or not masters:
        fail(f"{label} item {index}: m must be a non-empty master tag string")
    return {"m": masters, "t": text}


def category_from_spec(name: str, spec: dict, default_m: str) -> dict:
    defaults = {
        "style": ("STYLE", "Style", "Visual treatment and art direction", 22),
        "genre": ("GENRE", "Genre", "Narrative and thematic genre", 28),
    }
    key, label, note, order = defaults[name]
    raw_items = spec.get("items", [])
    if not isinstance(raw_items, list):
        fail(f"{name}.items must be an array")
    items = [normalize_item(item, default_m, name, i + 1) for i, item in enumerate(raw_items)]
    expected = spec.get("count")
    if expected is not None:
        if not isinstance(expected, int) or expected < 0:
            fail(f"{name}.count must be a non-negative integer")
        if len(items) != expected:
            fail(f"{name}: requested count is {expected}, but {len(items)} items were supplied")
    if len({item["t"] for item in items}) != len(items):
        fail(f"{name}: duplicate item text would be deduplicated by Prompt Bench and break the requested count")
    return {
        "key": spec.get("key", key),
        "label": spec.get("label", label),
        "note": spec.get("note", note),
        "order": spec.get("order", order),
        "items": items,
    }


def split_category_pack(pack_name: str, category: dict, max_bytes: int) -> list[dict]:
    if max_bytes <= 0 or max_bytes > MAX_UPLOAD:
        fail(f"max bytes must be between 1 and {MAX_UPLOAD}")
    items = category["items"]
    full = {"pack": pack_name, "categories": [category]}
    if len(dump_bytes(full)) <= max_bytes:
        return [full]
    if not items:
        fail("empty category metadata exceeds the configured file-size limit")

    # Chunk labels add bytes after splitting. Budget against a deliberately
    # longer placeholder so the real '(n/total)' label cannot overflow a part.
    budget_name = f"{pack_name} (999999/999999)"
    chunks: list[list[dict]] = []
    current: list[dict] = []
    for item in items:
        trial = current + [item]
        cat = dict(category)
        cat["items"] = trial
        obj = {"pack": budget_name, "categories": [cat]}
        if len(dump_bytes(obj)) <= max_bytes:
            current = trial
            continue
        if not current:
            fail(f"one category item alone exceeds the configured file-size limit: {item['t'][:80]!r}")
        chunks.append(current)
        current = [item]
        cat = dict(category)
        cat["items"] = current
        if len(dump_bytes({"pack": budget_name, "categories": [cat]})) > max_bytes:
            fail(f"one category item alone exceeds the configured file-size limit: {item['t'][:80]!r}")
    if current:
        chunks.append(current)

    out = []
    for i, chunk in enumerate(chunks, 1):
        cat = dict(category)
        cat["items"] = chunk
        name = f"{pack_name} ({i}/{len(chunks)})"
        obj = {"pack": name, "categories": [cat]}
        if len(dump_bytes(obj)) > max_bytes:
            fail("internal chunk sizing error: numbered pack exceeded max bytes")
        out.append(obj)
    return out


def validate_master(master: dict, where: str, errors: list[str]) -> None:
    if not isinstance(master, dict):
        errors.append(f"{where}: master must be an object")
        return
    mid = master.get("id")
    if not isinstance(mid, str) or len(mid) != 1 or mid.isspace():
        errors.append(f"{where}: master id must be one non-whitespace character")
    for key in ("name", "body"):
        if not isinstance(master.get(key), str) or not master[key].strip():
            errors.append(f"{where}: master {key} must be a non-empty string")
    if "blurb" in master and not isinstance(master["blurb"], str):
        errors.append(f"{where}: master blurb must be a string")
    if "inherits" in master:
        parent = master["inherits"]
        if not isinstance(parent, str) or len(parent) != 1:
            errors.append(f"{where}: inherits must be a single-character master id")


def validate_pack_object(obj, where: str, file_size: int | None = None) -> list[str]:
    errors: list[str] = []
    if file_size is not None and file_size > MAX_UPLOAD:
        errors.append(f"{where}: {file_size} bytes exceeds 512 KB")
    if not isinstance(obj, dict):
        return [f"{where}: pack must be a JSON object"]
    if not any(key in obj for key in KNOWN_KEYS):
        errors.append(f"{where}: contains none of Prompt Bench's recognised pack keys")
    unknown = set(obj) - KNOWN_KEYS
    if unknown:
        errors.append(f"{where}: unknown top-level keys: {', '.join(sorted(unknown))}")
    if "pack" in obj and (not isinstance(obj["pack"], str) or not obj["pack"].strip()):
        errors.append(f"{where}: pack must be a non-empty string")

    masters = obj.get("masters", [])
    if masters is not None:
        if not isinstance(masters, list):
            errors.append(f"{where}: masters must be an array")
        else:
            seen_ids = set()
            for i, master in enumerate(masters, 1):
                validate_master(master, f"{where} masters[{i}]", errors)
                if isinstance(master, dict) and isinstance(master.get("id"), str):
                    if master["id"] in seen_ids:
                        errors.append(f"{where}: duplicate master id {master['id']!r}")
                    seen_ids.add(master["id"])

    categories = obj.get("categories", [])
    if categories is not None:
        if not isinstance(categories, list):
            errors.append(f"{where}: categories must be an array")
        else:
            for ci, category in enumerate(categories, 1):
                loc = f"{where} categories[{ci}]"
                if not isinstance(category, dict):
                    errors.append(f"{loc}: category must be an object")
                    continue
                if not isinstance(category.get("key"), str) or not category["key"].strip():
                    errors.append(f"{loc}: key must be a non-empty string")
                if "order" in category and not isinstance(category["order"], (int, float)):
                    errors.append(f"{loc}: order must be numeric")
                items = category.get("items", [])
                if not isinstance(items, list):
                    errors.append(f"{loc}: items must be an array")
                    continue
                seen_text = set()
                for ii, item in enumerate(items, 1):
                    iloc = f"{loc} items[{ii}]"
                    if not isinstance(item, dict):
                        errors.append(f"{iloc}: item must be an object")
                        continue
                    text = item.get("t")
                    masters_tag = item.get("m", "ABC")
                    if not isinstance(text, str) or not text.strip():
                        errors.append(f"{iloc}: t must be a non-empty string")
                    elif text in seen_text:
                        errors.append(f"{iloc}: duplicate t text will be deduplicated by Prompt Bench")
                    else:
                        seen_text.add(text)
                    if not isinstance(masters_tag, str) or not masters_tag:
                        errors.append(f"{iloc}: m must be a non-empty string")

    for list_key in ("shared", "people", "dials", "variation", "fields"):
        if list_key in obj and not isinstance(obj[list_key], list):
            errors.append(f"{where}: {list_key} must be an array")
    return errors


def iter_pack_files(path: Path) -> list[Path]:
    if path.is_file():
        return [path]
    if path.is_dir():
        return sorted(path.rglob("*.json"))
    fail(f"not found: {path}")


def validate_path(path: Path) -> list[str]:
    errors: list[str] = []
    files = iter_pack_files(path)
    if not files:
        return [f"{path}: no JSON files found"]
    category_texts: dict[tuple[str, str], Path] = {}
    for file in files:
        try:
            raw = file.read_bytes()
            obj = json.loads(raw.decode("utf-8"))
        except UnicodeDecodeError:
            errors.append(f"{file}: must be UTF-8")
            continue
        except json.JSONDecodeError as exc:
            errors.append(f"{file}: invalid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}")
            continue
        errors.extend(validate_pack_object(obj, str(file), len(raw)))
        if isinstance(obj, dict):
            for category in obj.get("categories", []) or []:
                if not isinstance(category, dict) or not isinstance(category.get("key"), str):
                    continue
                key = category["key"]
                for item in category.get("items", []) or []:
                    if not isinstance(item, dict) or not isinstance(item.get("t"), str):
                        continue
                    token = (key, item["t"])
                    previous = category_texts.get(token)
                    if previous is not None:
                        errors.append(
                            f"{file}: duplicate {key} text also appears in {previous}; Prompt Bench would merge it"
                        )
                    else:
                        category_texts[token] = file
    return errors


def build(spec_path: Path, out_dir: Path, repo_root: Path, max_bytes: int, clean: bool) -> list[Path]:
    spec = load_json(spec_path)
    if not isinstance(spec, dict):
        fail("spec must be a JSON object")
    theme = spec.get("theme")
    if not isinstance(theme, str) or not theme.strip():
        fail("spec.theme must be a non-empty string")
    slug = slugify(spec.get("slug", theme))

    master_spec = spec.get("master")
    master_obj = None
    generated_master_id = None
    if master_spec is not None:
        if not isinstance(master_spec, dict):
            fail("spec.master must be an object or null")
        master_obj = dict(master_spec)
        if not master_obj.get("id") or str(master_obj.get("id")).upper() == "AUTO":
            master_obj["id"] = choose_master_id(repo_root)
        generated_master_id = master_obj["id"]
        master_errors: list[str] = []
        validate_master(master_obj, "spec.master", master_errors)
        if master_errors:
            fail("; ".join(master_errors))

    target_masters = spec.get("target_masters")
    if target_masters is None:
        target_masters = generated_master_id or "*"
    if not isinstance(target_masters, str) or not target_masters:
        fail("target_masters must be a non-empty string")

    outputs: list[tuple[str, dict]] = []
    if master_obj is not None:
        outputs.append((f"00-master-{slug}.json", {
            "pack": f"DLC: {theme} master",
            "masters": [master_obj],
        }))

    for kind, prefix in (("style", "20"), ("genre", "30")):
        block = spec.get(kind)
        if block is None:
            continue
        if not isinstance(block, dict):
            fail(f"spec.{kind} must be an object or null")
        category = category_from_spec(kind, block, target_masters)
        pack_name = block.get("pack", f"DLC: {theme} {kind}s")
        parts = split_category_pack(pack_name, category, max_bytes)
        if len(parts) == 1:
            outputs.append((f"{prefix}-{kind}-{slug}.json", parts[0]))
        else:
            width = max(2, len(str(len(parts))))
            for index, part in enumerate(parts, 1):
                outputs.append((f"{prefix}-{kind}-{slug}-{index:0{width}d}.json", part))

    if not outputs:
        fail("spec creates no files; include master, style, or genre")

    if clean and out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for filename, obj in outputs:
        path = out_dir / filename
        write_json(path, obj)
        written.append(path)

    errors = validate_path(out_dir)
    if errors:
        fail("generated bundle failed validation:\n- " + "\n- ".join(errors))
    return written


def init_spec(path: Path) -> None:
    if path.exists():
        fail(f"refusing to overwrite existing file: {path}")
    example = {
        "theme": "Example theme",
        "slug": "example-theme",
        "target_masters": None,
        "master": {
            "id": "AUTO",
            "name": "Example",
            "blurb": "What this master is for.",
            "inherits": "B",
            "body": "ROLE\nDescribe what the image should fundamentally be.\n\nWHAT CARRIES THE GROUP\nDescribe the compositional rule that should remain stable.",
        },
        "style": {
            "count": 2,
            "items": [
                "First distinct visual treatment, written as a positive instruction.",
                "Second distinct visual treatment, materially different from the first.",
            ],
        },
        "genre": {
            "count": 2,
            "items": [
                "First genre treatment with concrete visual/narrative cues.",
                "Second genre treatment with different cues and scene logic.",
            ],
        },
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(example, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Build and validate Prompt Bench DLC bundles")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_init = sub.add_parser("init", help="write an authoring spec template")
    p_init.add_argument("spec", type=Path)

    p_build = sub.add_parser("build", help="build master/style/genre JSON files from a spec")
    p_build.add_argument("spec", type=Path)
    p_build.add_argument("out", type=Path)
    p_build.add_argument("--repo-root", type=Path, default=repo_root_from_script())
    p_build.add_argument("--max-bytes", type=int, default=MAX_UPLOAD)
    p_build.add_argument("--clean", action="store_true", help="remove the output directory before building")

    p_validate = sub.add_parser("validate", help="validate a JSON pack or a directory of packs")
    p_validate.add_argument("path", type=Path)

    args = parser.parse_args(argv)
    try:
        if args.cmd == "init":
            init_spec(args.spec)
            print(f"wrote {args.spec}")
        elif args.cmd == "build":
            files = build(args.spec, args.out, args.repo_root, args.max_bytes, args.clean)
            print(f"PASS: generated {len(files)} file(s)")
            for path in files:
                print(path)
        else:
            errors = validate_path(args.path)
            if errors:
                print("FAIL", file=sys.stderr)
                for error in errors:
                    print(f"- {error}", file=sys.stderr)
                return 1
            print(f"PASS: {args.path}")
        return 0
    except PackError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
