"""python -m contracts validate NAME FILE  (NAME: results | capture | ledger_entry)"""

import json
import sys
from pathlib import Path

from jsonschema import ValidationError

from . import SCHEMAS, validate


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 3 or args[0] != "validate" or args[1] not in SCHEMAS:
        sys.exit(f"usage: python -m contracts validate {{{'|'.join(SCHEMAS)}}} FILE")
    path = Path(args[2])
    if not path.exists():
        sys.exit(f"FAIL: {path} not found")
    try:
        validate(args[1], json.loads(path.read_text()))
    except (ValidationError, ValueError) as exc:
        sys.exit(f"FAIL: {path} does not match contracts/{SCHEMAS[args[1]]}: {getattr(exc, 'message', exc)}")
    print(f"OK: {path} matches contracts/{SCHEMAS[args[1]]}")


if __name__ == "__main__":
    main()
