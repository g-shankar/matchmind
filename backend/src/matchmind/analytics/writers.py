"""Write tables in the Fabric Lakehouse layout.

    <out>/Tables/<table>/part-0.parquet     (or part-0.csv without pyarrow)
    <out>/Tables/<table>/_schema.json       columns, types, key, row count
    <out>/_manifest.json                    tables, row counts, format

Parquet needs `pyarrow` (extra `analytics`, Apache-2.0). Without it the same
tables are written as CSV by pure Python: UTF-8, LF line endings, `true`/`false`,
ISO-8601 UTC timestamps, empty for null. Output is deterministic: rows keep the
order they are given, and nothing in a file depends on the clock or the machine.
"""

from __future__ import annotations

import csv
import json
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .schema import ALL_TABLES, BY_NAME, SCHEMA_VERSION, Table

Row = dict[str, Any]
FORMATS = ("auto", "parquet", "csv")


def have_pyarrow() -> bool:
    try:
        import pyarrow  # noqa: F401
        import pyarrow.parquet  # noqa: F401
    except ImportError:
        return False
    return True


def resolve_format(fmt: str) -> str:
    if fmt not in FORMATS:
        raise ValueError(f"format must be one of {', '.join(FORMATS)}")
    if fmt == "auto":
        return "parquet" if have_pyarrow() else "csv"
    if fmt == "parquet" and not have_pyarrow():
        raise RuntimeError("Parquet needs pyarrow: pip install -e '.[analytics]' (or use --format csv)")
    return fmt


# ------------------------------------------------------------------- CSV


def _csv_cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")
    if isinstance(value, float):
        return repr(value)
    return str(value)


def _write_csv(table: Table, rows: list[Row], path: Path) -> None:
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh, lineterminator="\n")
        writer.writerow(table.names)
        for row in rows:
            writer.writerow([_csv_cell(row.get(name)) for name in table.names])


def _csv_value(text: str, dtype: str) -> Any:
    if text == "":
        return None
    if dtype == "int64":
        return int(text)
    if dtype == "float64":
        return float(text)
    if dtype == "bool":
        return text == "true"
    if dtype == "timestamp":
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    return text


# --------------------------------------------------------------- Parquet


def _arrow_type(dtype: str):
    import pyarrow as pa

    return {
        "string": pa.string(),
        "int64": pa.int64(),
        "float64": pa.float64(),
        "bool": pa.bool_(),
        "timestamp": pa.timestamp("us", tz="UTC"),
    }[dtype]


def _write_parquet(table: Table, rows: list[Row], path: Path) -> None:
    import pyarrow as pa
    import pyarrow.parquet as pq

    schema = pa.schema([pa.field(c.name, _arrow_type(c.dtype)) for c in table.cols])
    columns = [pa.array([r.get(c.name) for r in rows], type=schema.field(c.name).type) for c in table.cols]
    pq.write_table(pa.Table.from_arrays(columns, schema=schema), path, compression="snappy")


# ----------------------------------------------------------------- layout


def _schema_doc(table: Table, fmt: str, row_count: int) -> dict:
    return {
        "table": table.name,
        "kind": table.kind,
        "description": table.desc,
        "schema_version": SCHEMA_VERSION,
        "format": fmt,
        "file": f"part-0.{'parquet' if fmt == 'parquet' else 'csv'}",
        "row_count": row_count,
        "primary_key": list(table.key),
        "foreign_keys": dict(table.references),
        "columns": [{"name": c.name, "type": c.dtype, "description": c.desc} for c in table.cols],
    }


def _dump(doc: Any) -> str:
    return json.dumps(doc, indent=2, ensure_ascii=False) + "\n"


def write_tables(
    tables: dict[str, list[Row]],
    out: str | Path,
    fmt: str = "auto",
    *,
    matches: Iterable[str] = (),
) -> dict:
    """Write every table in `tables` under `out`. Returns the manifest."""
    fmt = resolve_format(fmt)
    root = Path(out)
    manifest_tables: dict[str, dict] = {}
    for table in ALL_TABLES:
        if table.name not in tables:
            continue
        rows = tables[table.name]
        folder = root / "Tables" / table.name
        folder.mkdir(parents=True, exist_ok=True)
        # A re-export in the other format must not leave the old part file behind:
        # Spark would read both into one table.
        for stale in [*folder.glob("part-*"), folder / "_schema.json"]:
            stale.unlink(missing_ok=True)
        doc = _schema_doc(table, fmt, len(rows))
        (_write_parquet if fmt == "parquet" else _write_csv)(table, rows, folder / doc["file"])
        (folder / "_schema.json").write_text(_dump(doc), encoding="utf-8")
        manifest_tables[table.name] = {"kind": table.kind, "rows": len(rows), "path": f"Tables/{table.name}"}
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "format": fmt,
        "matches": sorted(matches),
        "tables": manifest_tables,
    }
    root.mkdir(parents=True, exist_ok=True)
    (root / "_manifest.json").write_text(_dump(manifest), encoding="utf-8")
    return manifest


def read_table(root: str | Path, name: str) -> list[Row]:
    """Read a table back (either format), typed by its `_schema.json`."""
    folder = Path(root) / "Tables" / name
    doc = json.loads((folder / "_schema.json").read_text(encoding="utf-8"))
    path = folder / doc["file"]
    if doc["format"] == "parquet":
        import pyarrow.parquet as pq

        return pq.read_table(path).to_pylist()
    types = {c["name"]: c["type"] for c in doc["columns"]}
    with path.open(encoding="utf-8", newline="") as fh:
        return [{k: _csv_value(v, types[k]) for k, v in rec.items()} for rec in csv.DictReader(fh)]


def table_def(name: str) -> Table:
    return BY_NAME[name]
