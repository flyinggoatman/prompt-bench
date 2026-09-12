#!/usr/bin/env python3
"""Strict structural validator for every importable Prompt Bench pack mechanic."""
from __future__ import annotations

import json
import sys
from pathlib import Path

MAX_UPLOAD = 512 * 1024
KNOWN = {"pack", "private", "shared", "masters", "people", "categories", "dials", "variation", "fields"}


def num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def nonempty(v):
    return isinstance(v, str) and bool(v.strip())


def err(errors, where, message):
    errors.append(f"{where}: {message}")


def validate_master(x, where, errors):
    if not isinstance(x, dict):
        return err(errors, where, "master must be an object")
    mid = x.get("id")
    if not isinstance(mid, str) or len(mid) != 1 or mid.isspace():
        err(errors, where, "id must be one non-whitespace character")
    if not nonempty(x.get("name")):
        err(errors, where, "name must be a non-empty string")
    if not nonempty(x.get("body")):
        err(errors, where, "body must be a non-empty string")
    if "blurb" in x and not isinstance(x["blurb"], str):
        err(errors, where, "blurb must be a string")
    if "inherits" in x and (not isinstance(x["inherits"], str) or len(x["inherits"]) != 1):
        err(errors, where, "inherits must be one master id character")


def validate_shared(x, where, errors):
    if not isinstance(x, dict):
        return err(errors, where, "shared entry must be an object")
    if not nonempty(x.get("id")):
        err(errors, where, "id must be a non-empty string")
    if "label" in x and not isinstance(x["label"], str):
        err(errors, where, "label must be a string")
    blocks = x.get("blocks")
    if not isinstance(blocks, list):
        return err(errors, where, "blocks must be an array")
    for i, block in enumerate(blocks, 1):
        if not nonempty(block):
            err(errors, f"{where}.blocks[{i}]", "must be a non-empty string")


def validate_person(x, where, errors):
    if not isinstance(x, dict):
        return err(errors, where, "person must be an object")
    if not nonempty(x.get("id")):
        err(errors, where, "id must be a non-empty string")
    if not nonempty(x.get("name")):
        err(errors, where, "name must be a non-empty string")
    if x.get("kind", "person") not in ("person", "animal"):
        err(errors, where, "kind must be 'person' or 'animal'")
    for key in ("marker", "looks", "wears", "manner", "likes", "avoid"):
        if key in x and not isinstance(x[key], str):
            err(errors, where, f"{key} must be a string")


def validate_category(x, where, errors):
    if not isinstance(x, dict):
        return err(errors, where, "category must be an object")
    if not nonempty(x.get("key")):
        err(errors, where, "key must be a non-empty string")
    for key in ("label", "note"):
        if key in x and not isinstance(x[key], str):
            err(errors, where, f"{key} must be a string")
    if "order" in x and not num(x["order"]):
        err(errors, where, "order must be numeric")
    if "replace" in x and not isinstance(x["replace"], bool):
        err(errors, where, "replace must be boolean")
    items = x.get("items", [])
    if not isinstance(items, list):
        return err(errors, where, "items must be an array")
    seen = set()
    for i, item in enumerate(items, 1):
        iw = f"{where}.items[{i}]"
        if not isinstance(item, dict):
            err(errors, iw, "item must be an object")
            continue
        text = item.get("t")
        if not nonempty(text):
            err(errors, iw, "t must be a non-empty string")
        elif text in seen:
            err(errors, iw, "duplicate t text will be deduplicated by Prompt Bench")
        else:
            seen.add(text)
        tag = item.get("m", "ABC")
        if not nonempty(tag) or any(ch.isspace() for ch in tag):
            err(errors, iw, "m must be a non-empty compact master tag string")


def validate_dial(x, where, errors):
    if not isinstance(x, dict):
        return err(errors, where, "dial must be an object")
    if not nonempty(x.get("id")):
        err(errors, where, "id must be a non-empty string")
    if not nonempty(x.get("label")):
        err(errors, where, "label must be a non-empty string")
    for key in ("min", "max", "value", "order"):
        if key in x and not num(x[key]):
            err(errors, where, f"{key} must be numeric")
    for key in ("lo", "hi"):
        if key in x and not isinstance(x[key], (str, int, float)):
            err(errors, where, f"{key} must be text or a number")
    if "carryToFollowUp" in x and not isinstance(x["carryToFollowUp"], bool):
        err(errors, where, "carryToFollowUp must be boolean")
    minimum, maximum = x.get("min", 0), x.get("max", 10)
    value = x.get("value", minimum)
    if num(minimum) and num(maximum) and minimum > maximum:
        err(errors, where, "min must be <= max")
    if num(minimum) and num(maximum) and num(value) and not minimum <= value <= maximum:
        err(errors, where, "value must fall between min and max")
    stops = x.get("stops")
    if not isinstance(stops, list) or not stops:
        return err(errors, where, "stops must be a non-empty array")
    prev = None
    for i, stop in enumerate(stops, 1):
        sw = f"{where}.stops[{i}]"
        if not isinstance(stop, dict):
            err(errors, sw, "stop must be an object")
            continue
        up = stop.get("upTo")
        if not num(up):
            err(errors, sw, "upTo must be numeric")
        else:
            if prev is not None and up < prev:
                err(errors, sw, "upTo values must be ascending")
            prev = up
        if not nonempty(stop.get("text")):
            err(errors, sw, "text must be a non-empty string")
    if prev is not None and num(maximum) and prev < maximum:
        err(errors, where, "final stop should cover max")


def validate_variation(x, where, errors):
    if not isinstance(x, dict):
        return err(errors, where, "variation pool must be an object")
    if not nonempty(x.get("id")):
        err(errors, where, "id must be a non-empty string")
    if "order" in x and not num(x["order"]):
        err(errors, where, "order must be numeric")
    options = x.get("options")
    if not isinstance(options, list) or not options:
        return err(errors, where, "options must be a non-empty array")
    seen = set()
    for i, option in enumerate(options, 1):
        if not nonempty(option):
            err(errors, f"{where}.options[{i}]", "must be a non-empty string")
        elif option in seen:
            err(errors, f"{where}.options[{i}]", "duplicate option text")
        else:
            seen.add(option)


def validate_field(x, where, errors):
    if not isinstance(x, dict):
        return err(errors, where, "field must be an object")
    if not nonempty(x.get("id")):
        err(errors, where, "id must be a non-empty string")
    if not nonempty(x.get("label")):
        err(errors, where, "label must be a non-empty string")
    for key in ("hint", "placeholder", "default", "section", "wrap", "attachTo"):
        if key in x and not isinstance(x[key], str):
            err(errors, where, f"{key} must be a string")
    if "order" in x and not num(x["order"]):
        err(errors, where, "order must be numeric")
    if "rows" in x and (not isinstance(x["rows"], int) or isinstance(x["rows"], bool) or x["rows"] <= 0):
        err(errors, where, "rows must be a positive integer")
    if "splitList" in x and not isinstance(x["splitList"], bool):
        err(errors, where, "splitList must be boolean")
    if "limit" in x and (not isinstance(x["limit"], int) or isinstance(x["limit"], bool) or x["limit"] <= 0):
        err(errors, where, "limit must be a positive integer")
    if "carryToFollowUp" in x and not isinstance(x["carryToFollowUp"], bool):
        err(errors, where, "carryToFollowUp must be boolean")
    if "limit" in x and x.get("splitList") is not True:
        err(errors, where, "limit only has an effect when splitList is true")


def validate_object(obj, where, size=None):
    errors = []
    if size is not None and size > MAX_UPLOAD:
        err(errors, where, f"{size} bytes exceeds 512 KB")
    if not isinstance(obj, dict):
        return [f"{where}: pack must be a JSON object"]
    unknown = set(obj) - KNOWN
    if unknown:
        err(errors, where, f"unknown top-level keys: {', '.join(sorted(unknown))}")
    if not any(k in obj for k in KNOWN):
        err(errors, where, "contains none of Prompt Bench's recognised pack keys")
    if "pack" in obj and not nonempty(obj["pack"]):
        err(errors, where, "pack must be a non-empty string")
    if "private" in obj and not isinstance(obj["private"], bool):
        err(errors, where, "private must be boolean")

    validators = {
        "shared": validate_shared,
        "masters": validate_master,
        "people": validate_person,
        "categories": validate_category,
        "dials": validate_dial,
        "variation": validate_variation,
        "fields": validate_field,
    }
    for key, validator in validators.items():
        if key not in obj:
            continue
        values = obj[key]
        if not isinstance(values, list):
            err(errors, where, f"{key} must be an array")
            continue
        ids = set()
        for i, value in enumerate(values, 1):
            validator(value, f"{where}.{key}[{i}]", errors)
            if key != "categories" and isinstance(value, dict) and isinstance(value.get("id"), str):
                ident = value["id"]
                if ident in ids:
                    err(errors, where, f"duplicate {key} id {ident!r}")
                ids.add(ident)
    return errors


def files_for(path):
    if path.is_file():
        return [path]
    if path.is_dir():
        return sorted(path.rglob("*.json"))
    raise FileNotFoundError(path)


def validate_path(path):
    errors = []
    seen_category_text = {}
    files = files_for(path)
    if not files:
        return [f"{path}: no JSON files found"]
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
        errors.extend(validate_object(obj, str(file), len(raw)))
        if isinstance(obj, dict):
            for category in obj.get("categories", []) or []:
                if not isinstance(category, dict) or not isinstance(category.get("key"), str):
                    continue
                key = category["key"]
                for item in category.get("items", []) or []:
                    if not isinstance(item, dict) or not isinstance(item.get("t"), str):
                        continue
                    token = (key, item["t"])
                    if token in seen_category_text:
                        errors.append(f"{file}: duplicate {key} text also appears in {seen_category_text[token]}; Prompt Bench would merge it")
                    else:
                        seen_category_text[token] = file
    return errors


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print("usage: validate_mechanics.py <pack.json-or-directory>", file=sys.stderr)
        return 2
    path = Path(argv[0])
    try:
        errors = validate_path(path)
    except FileNotFoundError:
        print(f"FAIL\n- not found: {path}", file=sys.stderr)
        return 1
    if errors:
        print("FAIL", file=sys.stderr)
        for message in errors:
            print(f"- {message}", file=sys.stderr)
        return 1
    print(f"PASS: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
