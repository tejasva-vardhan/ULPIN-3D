"""Crop one public NYC 2017 LAS tile to an official tax lot for evaluation.

Run inside the backend image with --data-dir pointing to the public sample
directory. The full LAS tile can be downloaded with --download; it is ignored
by Git. Output coordinates and elevations are converted from US survey feet
to metres. This script does not create or infer ownership records.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from urllib.request import urlopen

import laspy
import numpy as np
from pyproj import CRS, Transformer
from shapely import intersects_xy
from shapely.geometry import mapping, shape
from shapely.ops import transform as shp_transform


FOOT_TO_METRE = 1200 / 3937
TILE_URL = "https://gisdata.ny.gov/elevation/LIDAR/NYC_TopoBathymetric2017/945172.las"
SAMPLES = {
    "684044": "5010700001",  # first case; kept as a baseline
    "836939": "5010700020",
    "150985": "5010680096",
}
FILES = {"945172.las": TILE_URL}
for _building_id, _bbl in SAMPLES.items():
    FILES[f"nyc_building_{_building_id}.json"] = (
        f"https://data.cityofnewyork.us/resource/5zhs-2jue.json?doitt_id={_building_id}")
    FILES[f"nyc_tax_lot_{_bbl}.json"] = (
        f"https://data.cityofnewyork.us/resource/i38t-6if2.json?bbl={_bbl}")
METRIC_EPSG = 32618
TILE_SHA256 = "2d0870ec64fd0fcd06bc0c6b9b516b47ee5c5602178b08844bacbecf24052a77"


def download_missing(root: Path):
    for name, url in FILES.items():
        path = root / name
        if path.exists():
            continue
        temporary = path.with_name(path.name + ".part")
        with urlopen(url, timeout=60) as response, temporary.open("wb") as output:
            while chunk := response.read(1024 * 1024):
                output.write(chunk)
        temporary.replace(path)
        print(f"Downloaded {name}")


def load_one(path: Path):
    rows = json.loads(path.read_text(encoding="utf-8"))
    if len(rows) != 1:
        raise ValueError(f"Expected exactly one official record in {path.name}")
    return rows[0]


def metric_polygon(record):
    geometry = shape(record["the_geom"])
    if geometry.geom_type == "MultiPolygon" and len(geometry.geoms) == 1:
        geometry = geometry.geoms[0]
    if geometry.geom_type != "Polygon" or not geometry.is_valid:
        raise ValueError("Expected one valid polygon")
    transformer = Transformer.from_crs(4326, METRIC_EPSG, always_xy=True)
    return shp_transform(transformer.transform, geometry)


def prepare(root: Path, building_id: str):
    bbl = SAMPLES[building_id]
    building_url = FILES[f"nyc_building_{building_id}.json"]
    building = load_one(root / f"nyc_building_{building_id}.json")
    lot = load_one(root / f"nyc_tax_lot_{bbl}.json")
    if building["doitt_id"] != building_id or building["base_bbl"] != lot["bbl"]:
        raise ValueError("Building and tax-lot identifiers do not match")
    reference = metric_polygon(building)
    parcel = metric_polygon(lot)
    if not parcel.buffer(0.05).covers(reference):
        raise ValueError("Reference footprint is not covered by the tax lot")

    source_path = root / "945172.las"
    with source_path.open("rb") as source:
        if hashlib.file_digest(source, "sha256").hexdigest() != TILE_SHA256:
            raise ValueError("Public LiDAR tile checksum differs from the documented sample")
    crop_path = root / f"lot_{bbl}_metre.las"
    with laspy.open(source_path) as reader:
        source_crs = reader.header.parse_crs()
        if source_crs is None or len(source_crs.axis_info) < 3:
            raise ValueError(f"Unexpected LiDAR horizontal CRS: {source_crs}")
        if any(abs(axis.unit_conversion_factor - FOOT_TO_METRE) > 1e-9
               for axis in source_crs.axis_info[:3]):
            raise ValueError("LiDAR coordinate and height units must be US survey feet")
        check = Transformer.from_crs(source_crs.to_2d(), 2263, always_xy=True)
        check_x, check_y = check.transform(*reader.header.mins[:2])
        if max(abs(check_x - reader.header.mins[0]),
               abs(check_y - reader.header.mins[1])) > 0.01:
            raise ValueError("LiDAR horizontal CRS does not match EPSG:2263")
        transform = Transformer.from_crs(source_crs.to_2d(), METRIC_EPSG, always_xy=True)
        region = parcel.buffer(6)
        arrays = {key: [] for key in ("x", "y", "z", "classification")}
        for points in reader.chunk_iterator(250_000):
            x, y = transform.transform(np.asarray(points.x), np.asarray(points.y))
            selected = intersects_xy(region, x, y)
            if selected.any():
                arrays["x"].append(np.asarray(x)[selected])
                arrays["y"].append(np.asarray(y)[selected])
                arrays["z"].append(np.asarray(points.z)[selected] * FOOT_TO_METRE)
                arrays["classification"].append(np.asarray(points.classification)[selected])
    selected_count = sum(len(chunk) for chunk in arrays["x"])
    if not 100 <= selected_count <= 2_000_000:
        raise ValueError(f"Unexpected crop size: {selected_count} points")
    header = laspy.LasHeader(point_format=6, version="1.4")
    header.add_crs(CRS.from_epsg(METRIC_EPSG))
    header.scales = [0.001, 0.001, 0.001]
    header.offsets = [float(min(map(np.min, arrays["x"]))),
                      float(min(map(np.min, arrays["y"]))), 0]
    cloud = laspy.LasData(header)
    for key in arrays:
        setattr(cloud, key, np.concatenate(arrays[key]))
    cloud.write(crop_path)

    case = {
        "case_id": f"nyc-2017-lidar-building-{building_id}",
        "data_kind": "real",
        "storage_epsg": METRIC_EPSG,
        "parcel": {"epsg": METRIC_EPSG, "geometry": mapping(parcel)},
        "reference": {
            "epsg": METRIC_EPSG,
            "footprint": mapping(reference),
            "height_m": float(building["height_roof"]) * FOOT_TO_METRE,
            "height_definition": "NYC HEIGHT_ROOF: roof above building ground elevation; source value in US survey feet, converted to metres; individual measurement method unspecified",
            "source": building_url,
        },
        "elevation": {
            "kind": "las", "path": crop_path.name,
            "epsg": METRIC_EPSG, "z_ref": "ORTHOMETRIC_NAVD88", "local_zero_m": 0,
        },
    }
    manifest = root / ("case.json" if building_id == "684044" else f"case_{building_id}.json")
    manifest.write_text(json.dumps(case, indent=2), encoding="utf-8")
    print(f"Prepared {selected_count} points and {manifest}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", required=True, type=Path)
    parser.add_argument("--download", action="store_true")
    parser.add_argument("--building-id", choices=SAMPLES, default="684044")
    args = parser.parse_args()
    args.data_dir.mkdir(parents=True, exist_ok=True)
    if args.download:
        download_missing(args.data_dir)
    prepare(args.data_dir, args.building_id)
