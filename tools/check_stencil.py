#!/usr/bin/env python3
"""Compare a Blueprint stencil with what rust-uasset read back from the built asset.

    uasset Content/Tests/BP_LogicTest.uasset > got.txt
    python3 tools/check_stencil.py docs/blueprints/BP_LogicTest.md got.txt

Prints the differences. A difference is not automatically a defect: Blueprint compilation reorders nodes
and omits empty overrides. A human decides.
"""
from __future__ import annotations

import difflib
import re
import sys
from pathlib import Path

FIELD = re.compile(r"^(Package|ParentClass):\s*(.+)$", re.M)


def graph_block(text: str) -> list[str]:
    """The fenced block that follows the Event graph heading."""
    m = re.search(r"#+\s*Event graph[^\n]*\n+```[^\n]*\n(.*?)```", text, re.S)
    if not m:
        return []
    out = []
    for line in m.group(1).splitlines():
        line = line.split("//")[0].rstrip()
        if line.strip():
            out.append(re.sub(r"\s+", " ", line.strip()))
    return out


SHORT_CLASS = {"Actor": "/Script/Engine.Actor", "Pawn": "/Script/Engine.Pawn",
               "Character": "/Script/Engine.Character", "ActorComponent": "/Script/Engine.ActorComponent",
               "SceneComponent": "/Script/Engine.SceneComponent", "Object": "/Script/CoreUObject.Object",
               "UserWidget": "/Script/UMG.UserWidget", "GameModeBase": "/Script/Engine.GameModeBase"}


def normalise_class(value: str) -> str:
    """A stencil may write `Actor`; rust-uasset prints `/Script/Engine.Actor`. Same class, one spelling."""
    value = value.strip().strip("`")
    return SHORT_CLASS.get(value, value)


def fields(text: str) -> dict[str, str]:
    out = {k: v.strip().strip("`") for k, v in FIELD.findall(text)}
    if "ParentClass" in out:
        out["ParentClass"] = normalise_class(out["ParentClass"])
    return out


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__)
        return 2
    stencil_path, got_path = (Path(a) for a in sys.argv[1:])
    stencil, got = stencil_path.read_text(encoding="utf-8"), got_path.read_text(encoding="utf-8")

    problems = []
    sf, gf = fields(stencil), fields(got)
    for key in ("Package", "ParentClass"):
        if key in sf and sf[key] != gf.get(key):
            problems.append(f"{key}: трафарет «{sf[key]}», в ассете «{gf.get(key, '—')}»")

    want, have = graph_block(stencil), graph_block(got)
    if not want:
        problems.append("в трафарете нет блока Event graph")
    elif not have:
        problems.append("в выводе uasset нет блока Event graph (ассет пуст или это не Blueprint)")
    elif want != have:
        diff = list(difflib.unified_diff(want, have, "трафарет", "ассет", lineterm="", n=1))
        problems.append("граф отличается:\n  " + "\n  ".join(diff))

    print(f"Трафарет: {stencil_path}\nАссет:    {got_path}\n")
    if not problems:
        print(f"Совпадает: {len(want)} строк графа, Package и ParentClass на месте.")
        return 0
    for p in problems:
        print("• " + p)
    print("\nРасхождение не всегда ошибка: компиляция переставляет узлы. Решает человек.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
