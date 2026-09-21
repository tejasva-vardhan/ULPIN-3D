"""Describe vertical floor divisions without overstating their evidence."""

import math

from shapely.geometry import shape

from app.geo import CrsError


def propose_floor_segmentation(ground_z: float, roof_z: float, *,
                               declared_storeys: int | None,
                               assumed_storey_height_m: float) -> dict:
    """Create review-required equal-height bands from a measured envelope."""
    height = roof_z - ground_z
    if not all(math.isfinite(value) for value in (ground_z, roof_z, assumed_storey_height_m)) or height <= 0:
        raise CrsError("Measured building elevations must define a finite positive height")
    if assumed_storey_height_m <= 0:
        raise CrsError("Assumed storey height must be positive")
    if declared_storeys is not None and (isinstance(declared_storeys, bool)
                                          or not isinstance(declared_storeys, int)
                                          or declared_storeys < 1):
        raise CrsError("Declared storeys must be a positive integer")
    if declared_storeys is None:
        floor_count = max(1, int(math.floor(height / assumed_storey_height_m + 0.5)))
        method = "HEIGHT_BANDS"
        evidence = "HEIGHT_INFERRED"
        count_basis = f"Measured height divided by an assumed {assumed_storey_height_m:g} m storey height"
    else:
        floor_count = declared_storeys
        method = "DECLARED_STOREYS"
        evidence = "OPERATOR_DECLARED"
        count_basis = "Storey count declared by the operator"
    if floor_count > 200:
        raise CrsError("Estimated floor count exceeds the prototype limit")
    step = height / floor_count
    boundaries = [ground_z + step * index for index in range(floor_count + 1)]
    boundaries[-1] = roof_z
    return {
        "method": method,
        "evidence": evidence,
        "floor_count": floor_count,
        "boundaries_m": [round(value, 6) for value in boundaries],
        "count_basis": count_basis,
        "equal_height_bands": True,
        "requires_review": True,
        "apartment_boundaries_supplied": False,
        "apartment_boundaries_observed": False,
    }


def describe_plan_segmentation(features: list[dict], building_code: str,
                               building_footprint) -> dict:
    """Validate and describe explicit floor volumes supplied by a plan dataset."""
    buildings = [feature for feature in features
                 if feature["properties"].get("local_code") == building_code
                 and feature["properties"].get("su_class") == "BUILDING"]
    if len(buildings) != 1:
        raise CrsError("Plan dataset must contain exactly one matching BUILDING feature")
    building_props = buildings[0]["properties"]
    try:
        building_min = float(building_props["zmin"])
        building_max = float(building_props["zmax"])
    except (KeyError, TypeError, ValueError) as exc:
        raise CrsError("Plan building requires finite zmin and zmax") from exc
    if (not math.isfinite(building_min) or not math.isfinite(building_max)
            or building_max <= building_min):
        raise CrsError("Plan building requires a positive finite height")
    floors = [feature for feature in features
              if feature["properties"].get("su_class") == "FLOOR"
              and feature["properties"].get("parent_code") == building_code]
    if not floors:
        raise CrsError("Plan dataset must contain at least one FLOOR for the matching building")

    levels = []
    seen_indices = set()
    for feature in floors:
        props = feature["properties"]
        code = props.get("local_code", "unnamed floor")
        index = props.get("level_index")
        if isinstance(index, bool) or not isinstance(index, int) or index in seen_indices:
            raise CrsError("Plan floors must have unique integer level_index values")
        seen_indices.add(index)
        try:
            zmin, zmax = float(props["zmin"]), float(props["zmax"])
        except (KeyError, TypeError, ValueError) as exc:
            raise CrsError(f"{code}: plan floor requires finite zmin and zmax") from exc
        if not math.isfinite(zmin) or not math.isfinite(zmax) or zmax <= zmin:
            raise CrsError(f"{code}: plan floor requires a positive finite height")
        if zmin < building_min - 0.05 or zmax > building_max + 0.05:
            raise CrsError(f"{code}: plan floor is outside the building height range")
        footprint = shape(feature["geometry"])
        if footprint.geom_type != "Polygon" or not building_footprint.buffer(0.03).covers(footprint):
            raise CrsError(f"{code}: plan floor footprint must be within the building footprint")
        levels.append({"local_code": code, "level_index": index,
                       "zmin": zmin, "zmax": zmax,
                       "label": str(props.get("label", index))})

    levels.sort(key=lambda level: (level["zmin"], level["zmax"]))
    warnings = []
    for previous, current in zip(levels, levels[1:]):
        overlap = previous["zmax"] - current["zmin"]
        if overlap > 0.05:
            raise CrsError(
                f"Plan floors {previous['local_code']} and {current['local_code']} overlap vertically"
            )
        gap = current["zmin"] - previous["zmax"]
        if gap > 0.05:
            warnings.append({"rule": "FLOOR_GAP", "after": previous["local_code"],
                             "before": current["local_code"], "gap_m": round(gap, 6)})

    floor_codes = {level["local_code"] for level in levels}
    apartment_count = sum(
        feature["properties"].get("su_class") == "UNIT"
        and feature["properties"].get("parent_code") in floor_codes | {building_code}
        for feature in features
    )
    relevant = [feature for feature in features
                if feature["properties"].get("local_code") == building_code
                or feature["properties"].get("parent_code") in floor_codes | {building_code}]
    return {
        "method": "PLAN_LEVELS",
        "evidence": "PLAN_SUPPLIED",
        "floor_count": len(levels),
        "levels": levels,
        "equal_height_bands": False,
        "requires_review": any(feature["properties"].get("requires_review", False)
                               for feature in relevant),
        "apartment_boundaries_supplied": apartment_count > 0,
        "apartment_boundary_count": apartment_count,
        "apartment_boundaries_observed": False,
        "warnings": warnings,
    }
