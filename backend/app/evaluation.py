"""Opt-in, source-traceable single-building evaluation of the existing estimator.

Run: python -m app.evaluation CASE.json [CASE2.json ...] --output REPORT.json
No database or browser is needed. Use --help for the case manifest format.
A reported error is meaningful only if reference
geometry and height were measured independently of the elevation input.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from statistics import median
from time import perf_counter

from pyproj import CRS, Transformer
from shapely.geometry import shape, mapping
from shapely.ops import transform as shp_transform

from app.geo import CrsError, require_epsg
from app.pipeline.assets import checksum_file, inspect_asset
from app.pipeline.measure import measure_cloud, measure_rasters

STORAGE_EPSG = 32643


def case_schema():
    """Required JSON fields and their meanings; paths are relative to the manifest.

    {"case_id": "unique label", "data_kind": "real|synthetic",
     "parcel": {"epsg": 32643, "geometry": "GeoJSON Polygon"},
     "reference": {"source": "independent survey/report URL or description",
                   "epsg": 32643, "footprint": "GeoJSON Polygon",
                   "height_m": 9.2,
                   "height_definition": "roof above local ground; state method"},
     "elevation": {"kind": "las", "path": "crop.laz",
                   "z_ref": "ORTHOMETRIC_EGM", "local_zero_m": 430.0}}
    For rasters, elevation has kind=dsm_dtm, dsm="dsm.tif", dtm="dtm.tif",
    z_ref and local_zero_m. A single declared offset applies to both files.
    Supported source EPSG is read from each file, or explicitly supplied.
    """


def _polygon(item, label):
    epsg = require_epsg(item.get("epsg"))
    if not CRS.from_epsg(epsg).is_projected and epsg != 4326:
        raise CrsError(f"{label} EPSG must be projected or EPSG:4326")
    raw = item.get("geometry", item.get("footprint"))
    try:
        if not isinstance(raw, dict):
            raise ValueError("GeoJSON Polygon object is required")
        geom = shape(raw)
        if geom.geom_type != "Polygon" or geom.is_empty or not geom.is_valid or geom.area == 0:
            raise ValueError("expected one valid nonempty Polygon")
        if geom.has_z:
            raise ValueError("reference polygons must be 2D")
        if epsg != STORAGE_EPSG:
            tr = Transformer.from_crs(epsg, STORAGE_EPSG, always_xy=True)
            geom = shp_transform(tr.transform, geom)
        if not geom.is_valid or not math.isfinite(geom.area) or geom.area <= 0:
            raise ValueError("reprojected polygon is invalid")
        return geom
    except (AttributeError, TypeError, KeyError, ValueError) as exc:
        raise CrsError(f"{label}: {exc}") from exc


def _source_file(manifest_path, value, kind, epsg=None):
    if not isinstance(value, str) or not value.strip():
        raise CrsError(f"{kind} file path is required")
    path = (manifest_path.parent / value).resolve()
    if not path.is_file():
        raise CrsError(f"Missing {kind} file: {path}")
    info = inspect_asset(path, kind, epsg)
    return path, info


def _finite_height(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
        raise CrsError("Reference height_m must be a positive finite number of metres")
    return float(value)


def evaluate_case(manifest_path):
    manifest_path = Path(manifest_path).resolve()
    try:
        case = json.loads(manifest_path.read_text(encoding="utf-8"))
        case_id = case["case_id"]
        kind = case["data_kind"]
        if kind not in {"real", "synthetic"} or not isinstance(case_id, str) or not case_id.strip():
            raise CrsError("case_id and data_kind=real|synthetic are required")
        parcel = _polygon(case["parcel"], "parcel")
        longitude = Transformer.from_crs(STORAGE_EPSG, 4326, always_xy=True).transform(
            parcel.centroid.x, parcel.centroid.y)[0]
        if not 72 <= longitude < 78:
            raise CrsError("Parcel is outside the EPSG:32643 longitude zone (72–78°E)")
        reference = case["reference"]
        footprint = _polygon(reference, "reference footprint")
        reference_height = _finite_height(reference["height_m"])
        if not parcel.buffer(0.05).covers(footprint):
            raise CrsError("Reference footprint lies outside the parcel")
        source = reference["source"]
        definition = reference["height_definition"]
        if not isinstance(source, str) or not source.strip() or not isinstance(definition, str) or not definition.strip():
            raise CrsError("Independent reference source and height_definition are required")
        elevation = case["elevation"]
        mode = elevation["kind"]
        if mode not in {"las", "dsm_dtm"}:
            raise CrsError("elevation.kind must be las or dsm_dtm")
        offset = elevation["local_zero_m"]
        if isinstance(offset, bool) or not isinstance(offset, (int, float)) or not math.isfinite(offset):
            raise CrsError("A finite local_zero_m is required")
        z_ref = elevation["z_ref"]
        if z_ref not in {"LOCAL_SITE", "ORTHOMETRIC_EGM", "ELLIPSOIDAL_WGS84"}:
            raise CrsError("Unsupported vertical reference")
        if z_ref == "LOCAL_SITE" and offset != 0:
            raise CrsError("LOCAL_SITE data must use zero local_zero_m")
        inputs = []
        if mode == "las":
            path, info = _source_file(manifest_path, elevation["path"], "las", elevation.get("epsg"))
            inputs.append({"path": str(path), "sha256": checksum_file(path), "epsg": info["source_epsg"], "kind": "las"})
            start = perf_counter()
            measured = measure_cloud(path, info["source_epsg"], offset, parcel)
        else:
            paths = []
            for label in ("dsm", "dtm"):
                path, info = _source_file(manifest_path, elevation[label], label, elevation.get("epsg"))
                paths.append((path, info))
                inputs.append({"path": str(path), "sha256": checksum_file(path), "epsg": info["source_epsg"], "kind": label})
            start = perf_counter()
            measured = measure_rasters(paths[0][0], paths[1][0],
                {"source_epsg": paths[0][1]["source_epsg"], "local_zero_m": offset},
                {"source_epsg": paths[1][1]["source_epsg"], "local_zero_m": offset}, parcel)
        elapsed = perf_counter() - start
        predicted = measured["footprint"]
        overlap = predicted.intersection(footprint).area
        union = predicted.union(footprint).area
        height_error = measured["height_m"] - reference_height
        return {
            "case_id": case_id, "data_kind": kind,
            "reference": {"source": source, "height_definition": definition,
                          "height_m": reference_height, "footprint": mapping(footprint)},
            "inputs": inputs, "local_zero_m": offset, "z_ref": z_ref,
            "estimator": {"method": measured["method"], "height_m": measured["height_m"],
                          "footprint": mapping(predicted),
                          "assumptions": measured["assumptions"], "confidence": measured["confidence"],
                          "confidence_kind": measured["confidence_kind"]},
            "geometry_epsg": STORAGE_EPSG,
            "metrics": {"footprint_iou": overlap / union,
                        "footprint_area_bias_m2": predicted.area - footprint.area,
                        "centroid_error_m": predicted.centroid.distance(footprint.centroid),
                        "height_error_m": height_error,
                        "height_absolute_error_m": abs(height_error),
                        "height_relative_error_percent": 100 * height_error / reference_height,
                        "elapsed_seconds": elapsed},
            "note": "Reference independence is declared by the case author, not verified by this program. No legal boundary or floor accuracy is inferred."
        }
    except (KeyError, TypeError, json.JSONDecodeError) as exc:
        raise CrsError(f"Invalid case manifest {manifest_path}: {exc}") from exc


def evaluate_cases(paths):
    results = [evaluate_case(path) for path in paths]
    ids = [r["case_id"] for r in results]
    if len(ids) != len(set(ids)):
        raise CrsError("Each evaluation case_id must be unique")
    real = [r for r in results if r["data_kind"] == "real"]
    summary = {"all_case_count": len(results), "real_case_count": len(real),
               "synthetic_case_count": len(results) - len(real)}
    if real:
        summary["real_only"] = {
            "median_footprint_iou": median(r["metrics"]["footprint_iou"] for r in real),
            "median_height_absolute_error_m": median(r["metrics"]["height_absolute_error_m"] for r in real),
        }
    else:
        summary["real_only"] = None
    return {"summary": summary, "cases": results}


def main():
    parser = argparse.ArgumentParser(description=__doc__, epilog=case_schema.__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("cases", nargs="+", type=Path, help="case JSON manifests with paths relative to each manifest")
    parser.add_argument("--output", type=Path, required=True, help="where to write the evaluation JSON report")
    args = parser.parse_args()
    report = evaluate_cases(args.cases)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Wrote {len(report['cases'])} case(s); real: {report['summary']['real_case_count']}; {args.output}")


if __name__ == "__main__":
    main()
