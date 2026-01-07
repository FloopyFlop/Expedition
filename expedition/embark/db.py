from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class DroneRecord:
    key: str
    data: dict[str, Any]


def load_db(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"updated_at": None, "drones": [], "conflicts": []}
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def save_db(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data["updated_at"] = _utc_now()
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, sort_keys=True)
        handle.write("\n")


def upsert_drone(db: dict[str, Any], record: dict[str, Any]) -> DroneRecord | None:
    name = _normalize_text(record.get("name"))
    manufacturer = _normalize_text(record.get("manufacturer"))
    if not name:
        return None
    key = _make_key(name, manufacturer)

    drones = db.setdefault("drones", [])
    conflicts = db.setdefault("conflicts", [])

    existing = next((item for item in drones if item.get("key") == key), None)
    if not existing:
        new_entry = {
            "key": key,
            "name": record.get("name"),
            "manufacturer": record.get("manufacturer"),
            "category": record.get("category"),
            "weight_kg": record.get("weight_kg"),
            "max_payload_kg": record.get("max_payload_kg"),
            "flight_time_minutes": record.get("flight_time_minutes"),
            "range_km": record.get("range_km"),
            "max_speed_kmh": record.get("max_speed_kmh"),
            "sensors": record.get("sensors") or [],
            "notes": record.get("notes") or "",
            "sources": [record.get("source_url")] if record.get("source_url") else [],
            "first_seen_at": _utc_now(),
            "last_seen_at": _utc_now(),
        }
        drones.append(new_entry)
        return DroneRecord(key=key, data=new_entry)

    _merge_field(existing, record, "category", conflicts, key)
    _merge_field(existing, record, "weight_kg", conflicts, key)
    _merge_field(existing, record, "max_payload_kg", conflicts, key)
    _merge_field(existing, record, "flight_time_minutes", conflicts, key)
    _merge_field(existing, record, "range_km", conflicts, key)
    _merge_field(existing, record, "max_speed_kmh", conflicts, key)

    new_sensors = record.get("sensors") or []
    if new_sensors:
        existing_sensors = set(existing.get("sensors") or [])
        existing_sensors.update([s for s in new_sensors if s])
        existing["sensors"] = sorted(existing_sensors)

    new_notes = record.get("notes")
    if new_notes and new_notes not in (existing.get("notes") or ""):
        if existing.get("notes"):
            existing["notes"] = f"{existing['notes']} | {new_notes}"
        else:
            existing["notes"] = new_notes

    source_url = record.get("source_url")
    if source_url:
        sources = set(existing.get("sources") or [])
        sources.add(source_url)
        existing["sources"] = sorted(sources)

    existing["last_seen_at"] = _utc_now()
    return DroneRecord(key=key, data=existing)


def _merge_field(
    existing: dict[str, Any],
    record: dict[str, Any],
    field: str,
    conflicts: list[dict[str, Any]],
    key: str,
) -> None:
    incoming = record.get(field)
    if incoming is None or incoming == "":
        return
    current = existing.get(field)
    if current is None or current == "":
        existing[field] = incoming
        return
    if current != incoming:
        conflicts.append(
            {
                "key": key,
                "field": field,
                "current": current,
                "incoming": incoming,
                "source_url": record.get("source_url"),
                "observed_at": _utc_now(),
            }
        )


def _normalize_text(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).strip().lower().split())


def _make_key(name: str, manufacturer: str) -> str:
    return f"{manufacturer}|{name}" if manufacturer else name


def _utc_now() -> str:
    return datetime.now(tz=timezone.utc).isoformat()
