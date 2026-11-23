#!/usr/bin/env python3
"""Thin wrapper: passes every argument through to sk_entry.py.

`python run_skill.py --input ... --work ... --out ...` is equivalent to
`python sk_entry.py --input ... --work ... --out ...`. Import failures and
unexpected exceptions are contained here so the harness never sees a traceback
or a non-zero exit code; a minimal result.json is still written.
"""

import json
import os
import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from sk_entry import main as sk_main
except BaseException:
    sk_main = None


def _out_path(argv):
    value = "/app/output"
    index = 0
    while index < len(argv):
        token = argv[index]
        for flag in ("--out", "--output"):
            if token == flag and index + 1 < len(argv):
                value = argv[index + 1]
                index += 2
                break
            if token.startswith(flag + "="):
                value = token.split("=", 1)[1]
                index += 1
                break
        else:
            index += 1
    path = Path(value)
    return path if path.suffix.lower() == ".json" else path / "result.json"


def _fallback(argv):
    payload = {
        "case_id": "unknown",
        "status": "failed",
        "result": {"trend_overview": {"status": "not_produced",
                                      "reason": "the wrapper could not import or run sk_entry"}},
        "evidence": [],
        "uncertainty": [{"type": "run_failure", "detail": "entry wrapper fallback"}],
        "errors": [{"stage": "wrapper", "type": "entry_failure", "message": "sk_entry could not be executed"}],
        "stats": {"network": "disabled"},
        "contract_notes": {},
    }
    try:
        target = _out_path(argv)
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
    except BaseException:
        pass


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    try:
        if sk_main is None:
            raise RuntimeError("sk_entry import failed")
        sk_main(argv)
    except BaseException:
        _fallback(argv)
    return 0


if __name__ == "__main__":
    try:
        main()
    except BaseException:
        pass
    sys.exit(0)
