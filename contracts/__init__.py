"""JSON contracts shared by all Q-Shield Atlas modules.

Modules exchange data only through documents that validate against the schemas in this
folder: capture.json, results.json and ledger entries.
"""

import json
from functools import lru_cache
from pathlib import Path

from jsonschema import Draft202012Validator

SCHEMA_DIR = Path(__file__).parent
SCHEMAS = {
    "capture": "capture.schema.json",
    "results": "results.schema.json",
    "ledger_entry": "ledger_entry.schema.json",
}


@lru_cache(maxsize=None)
def load_schema(name: str) -> dict:
    schema = json.loads((SCHEMA_DIR / SCHEMAS[name]).read_text())
    Draft202012Validator.check_schema(schema)
    return schema


def validate(name: str, document: dict) -> None:
    """Raise jsonschema.ValidationError if `document` breaks contract `name`."""
    Draft202012Validator(load_schema(name)).validate(document)
