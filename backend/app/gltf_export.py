from __future__ import annotations

import base64
import json
import struct

from shapely import wkt as shapely_wkt


def prisms_to_gltf(rows: list[dict]) -> bytes:
    """Minimal glTF 2.0 of unit prisms in local metres (not a legal CAD model)."""
    positions: list[float] = []
    indices: list[int] = []
    origin = None
    for row in rows:
        poly = shapely_wkt.loads(row["wkt"])
        ring = list(poly.exterior.coords)[:-1]
        if len(ring) < 3:
            continue
        if origin is None:
            origin = (ring[0][0], ring[0][1])
        z0, z1 = float(row["zmin"]), float(row["zmax"])
        base = len(positions) // 3
        n = len(ring)
        for x, y in ring:
            positions.extend([x - origin[0], y - origin[1], z0])
        for x, y in ring:
            positions.extend([x - origin[0], y - origin[1], z1])
        for i in range(1, n - 1):
            indices.extend([base, base + i, base + i + 1])
            indices.extend([base + n, base + n + i + 1, base + n + i])
        for i in range(n):
            j = (i + 1) % n
            a, b = base + i, base + j
            c, d = base + n + i, base + n + j
            indices.extend([a, b, d, a, d, c])

    if origin is None:
        raise ValueError("no prisms to export")

    p_bytes = b"".join(struct.pack("<f", v) for v in positions)
    i_bytes = b"".join(struct.pack("<H", v) for v in indices)
    if len(i_bytes) % 4:
        i_bytes += b"\x00\x00"
    blob = p_bytes + i_bytes
    uri = "data:application/octet-stream;base64," + base64.b64encode(blob).decode("ascii")
    n_pos = len(positions) // 3
    xs, ys, zs = positions[0::3], positions[1::3], positions[2::3]
    doc = {
        "asset": {
            "version": "2.0",
            "generator": "Stratum proposed prisms (not official cadastral CAD)",
        },
        "buffers": [{"uri": uri, "byteLength": len(blob)}],
        "bufferViews": [
            {"buffer": 0, "byteOffset": 0, "byteLength": len(p_bytes), "target": 34962},
            {"buffer": 0, "byteOffset": len(p_bytes), "byteLength": len(indices) * 2, "target": 34963},
        ],
        "accessors": [
            {
                "bufferView": 0,
                "componentType": 5126,
                "count": n_pos,
                "type": "VEC3",
                "min": [min(xs), min(ys), min(zs)],
                "max": [max(xs), max(ys), max(zs)],
            },
            {"bufferView": 1, "componentType": 5123, "count": len(indices), "type": "SCALAR"},
        ],
        "meshes": [{"primitives": [{"attributes": {"POSITION": 0}, "indices": 1, "mode": 4}]}],
        "nodes": [{"mesh": 0, "name": "legal_prisms_local_m"}],
        "scenes": [{"nodes": [0]}],
        "scene": 0,
        "extras": {
            "origin_utm43n_m": origin,
            "note": "proposed 3D legal prisms for demo. Not an official ULPIN product.",
        },
    }
    return json.dumps(doc).encode("utf-8")
