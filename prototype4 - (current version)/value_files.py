"""Export saved transfer values from History."""

import csv
import json
from pathlib import Path

from Capstone2.prototype4.variable_transfer_v2 import normalise_value


FORMAT_NAME = "grasshopper-habsim-transfer-values"
FORMAT_VERSION = 1


def record_value_rows(record):
    """Return all values known for a history record, including legacy records."""
    rows = []
    changes = record.get("changes", {})
    mappings = record.get("mappings", {})

    for item in record.get("transferred_variables", []):
        if isinstance(item, str):
            source = item
            destination = mappings.get(source, source)
            item = {"source": source, "destination": destination}

        source = item.get("source", "")
        destination = item.get("destination", mappings.get(source, source))
        change = changes.get(destination, {})

        before = item.get("before", change.get("before"))
        after = item.get("after", item.get("value", change.get("after")))

        rows.append({
            "source": source,
            "destination": destination,
            "before": before,
            "after": after,
            "value": after,
        })

    # Very old records may contain changes without a transferred_variables list.
    existing_destinations = {row["destination"] for row in rows}
    for destination, change in changes.items():
        if destination in existing_destinations:
            continue
        rows.append({
            "source": change.get("source", destination),
            "destination": destination,
            "before": change.get("before"),
            "after": change.get("after"),
            "value": change.get("after"),
        })

    return rows


def _payload(record):
    return {
        "format": FORMAT_NAME,
        "version": FORMAT_VERSION,
        "transfer": {
            "id": record.get("id"),
            "timestamp": record.get("timestamp"),
            "source_file": record.get("source_file"),
            "destination_file": record.get("destination_file"),
            "mode": record.get("mode"),
        },
        "values": record_value_rows(record),
    }


def export_transfer_values(record, path):
    """Export one History transfer to JSON, TXT, or CSV."""
    path = Path(path)
    extension = path.suffix.lower()
    rows = record_value_rows(record)

    if not rows:
        raise ValueError("This history record does not contain any exportable values.")

    if extension == ".json":
        path.write_text(json.dumps(_payload(record), indent=2), encoding="utf-8")

    elif extension == ".txt":
        lines = [
            "# Grasshopper-HabSim transfer values",
            f"# timestamp: {record.get('timestamp', '')}",
            f"# source: {record.get('source_file', '')}",
            f"# destination: {record.get('destination_file', '')}",
            "source_variable\tdestination_variable\tvalue\tbefore\tafter",
        ]
        for row in rows:
            lines.append("\t".join(
                "" if row.get(key) is None else str(row.get(key))
                for key in ("source", "destination", "value", "before", "after")
            ))
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    elif extension == ".csv":
        with open(path, "w", newline="", encoding="utf-8-sig") as file:
            writer = csv.writer(file)
            writer.writerow([
                "Source Variable",
                "Destination Variable",
                "Value",
                "Before",
                "After",
            ])

            for row in rows:
                writer.writerow([
                    row.get("source", ""),
                    row.get("destination", ""),
                    "" if row.get("value") is None else str(row.get("value")),
                    "" if row.get("before") is None else str(row.get("before")),
                    "" if row.get("after") is None else str(row.get("after")),
                ])

    else:
        raise ValueError("Choose a .json, .txt, or .csv file.")

    return str(path)
