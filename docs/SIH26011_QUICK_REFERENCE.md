# SIH26011 — Quick Technical Reference

**3D ULPIN Generation and Vertical Property Mapping**  
DoLR / Ministry of Rural Development · Software · Smart Automation  
Official PS: [sih.gov.in/sih2026PS](https://www.sih.gov.in/sih2026PS) (verified 18 Sep 2026)  
**Rule:** Our 3D ULPIN is a **proposed extension** compatible with existing ULPIN. It is not an official Government format.

---

## WHAT

A working 3D cadastral prototype that:

- takes a **2D land parcel** (and optional LiDAR/DSM + floor plans + utilities),
- builds **legal 3D volumes** for the lot, floors, apartments, common areas, parking, and underground corridors,
- **validates topology** with geometry (not a neural net),
- issues a **proposed 3D ULPIN** nested under the official 14-character surface ULPIN,
- stores LADM-aligned records in PostGIS and shows them on a Cesium globe.

Working name: **ULPIN-3D**. Demo scale: **one Indian urban parcel, one multi-storey building**.

---

## WHY

DoLR: ULPIN is a **14-character** ID from parcel **lat/long vertices**; the ID “would spatially be pointing to the **surface** of the parcel.”

So one official ULPIN cannot uniquely name Flat 501, a basement, an air-rights slab, or a sewer under the same plot. That is the problem SIH26011 asks us to solve.

No public official **3D ULPIN standard** was found (DoLR / DILRMP / NGP 2022). We propose an extension; we do not mint government IDs.

---

## INPUT

SIH portal dataset field is **empty**. We do **not** claim SVAMITVA or state cadastral dumps.

| Input | MVP source | Honest note |
|---|---|---|
| Cadastral polygon | Authored GeoJSON in EPSG:32643 | Format-compatible with GIS; not a live Bhu-Naksha feed |
| Parent ULPIN | 14-char placeholder or ingested string | Labelled official-or-placeholder |
| Point cloud / DSM | Synthetic LAS **or** public ALS for metrics | Indian ALS (TALD) only if we actually obtain it |
| Floor plans | Digitised GeoJSON | Not scanned PDFs in MVP |
| Utilities | 3D line GeoJSON + diameter | Schematic |
| DEM | Optional; CartoDEM ~30 m | Too coarse for floors — terrain context only |
| GNSS/CORS | CRS + accuracy metadata | No live CORS client |

Missing CRS = **hard fail**. Missing LiDAR or plans = **degraded path**, not a crash.

---

## PIPELINE

```
Input → CRS/QA → nDSM/footprint → height/floors → extrude solids
      → underground buffers → topology rules → proposed 3D ULPIN
      → PostGIS → API → Cesium
```

| Stage | Tech | Why that tech |
|---|---|---|
| I/O, CRS | GDAL, pyproj, PDAL | Industry default; LAS/LAZ + raster |
| Ground / nDSM | PDAL CSF | No training data |
| Footprint | Open3D + morph/planarity | Explainable; works on ALS |
| Floors | Z-histogram / RANSAC, **plans win** | Airborne LiDAR does not see slabs |
| Solids | PostGIS SFCGAL `CG_Extrude` | Real volume + 3D intersection |
| Topology | SQL + Shapely/GEOS | Deterministic, demo-able errors |
| IDs | Python issuer | UUID stable; display string hierarchical |
| API | FastAPI | Same language as the geometry stack |
| UI | CesiumJS | Globe, underground, WGS84 |

**AI policy:** classical geometry is the MVP “automation.” Topology is never ML. Deep models only if time remains, and never as legal truth.

---

## OUTPUT

For each legal space:

1. `ulpin3d_uuid` (immutable)
2. Display ID: `IN-ULPIN3D/{parent_ulpin}/{CLASS}/{local}/vNN`  
   Example: `IN-ULPIN3D/12AB34CD56EF78/UNIT/F05-U501/v01`
3. 2D footprint + `zmin/zmax` + 3D prism solid + volume
4. `geom_origin` = SURVEY \| PLAN \| AI_DERIVED \| SYNTHETIC \| MANUAL
5. confidence 0–1, topology VALID/INVALID, source checksums

Physical building mesh ≠ legal unit. Common corridor is `COMMON` with undivided share (RERA / apartment acts), not a fake private title.

---

## DEMO (judges, ~4 minutes)

Scene: synthetic **Pune** parcel, real UTM 43N.

1. 2D parcel + parent ULPIN  
2. Load cloud/DSM → extract building → extrude  
3. Floors → click Flat 501 → cyan volume + 3D ULPIN  
4. Slice Z → show underground pipe  
5. Load overlapping fake unit → **INVALID** (red) → fix → **VALID** card  

First sentence: *Official ULPIN names the land. We name the volume.*

---

## MVP (must work)

- 1 parcel, 1 building, ≥4 storeys, ≥2 units/floor, 1 COMMON, 1 parking, 1 utility  
- Ingest GeoJSON + LAS/DSM + plans  
- Proposed 3D ULPIN under parent ULPIN  
- Topology with injected error  
- Cesium: isolate floor, underground toggle, provenance  
- LADM-aligned schema (not “ISO certified”)

## FUTURE (not MVP)

IFC ingest, CityGML export, RandLA-Net, live CORS, city-scale 3D Tiles, real SVAMITVA data, legally binding titles.

---

## RISKS

| # | Risk | Mitigation |
|---|---|---|
| 1 | No official Indian LAS | Synthetic georeferenced demo; label sources |
| 2 | ALS cannot see floors | Floor plans first; height heuristic flagged |
| 3 | ID overclaim | PROPOSED banner; parent ULPIN immutable |
| 4 | Dirty polygons break solids | MakeValid + always store 2.5D params |
| 5 | DL rabbit hole | Freeze classical pipeline |
| 6 | Silent CRS errors | Hard-fail missing EPSG |
| 7 | Cesium underground | Translucency; 2D fallback |
| 8 | Scope creep | One building |
| 9 | Legal overclaim | “Not a title” + geom_origin |
| 10 | Unstable IDs | UUID never recycled |

---

## JUDGE DEFENSE (short)

| Question | Answer |
|---|---|
| Why not 2D ULPIN? | It points at the **surface** (DoLR). One XY, many rights. |
| Why not a building ID? | Building is physical; cadastre is **legal space** + RRR (ISO 19152). |
| Official 3D ULPIN? | **No.** Proposed extension under the 14-char parent. |
| Common areas? | Undivided share to association (RERA s.17). Class `COMMON`. |
| Underground? | Corridor solids + easement-style RRR. Not a new statute. |
| Accuracy? | Demo metrics only. Plans ~0.3 m Z. CartoDEM is not floors. |
| No LiDAR / no plans? | Degraded prisms; confidence drops; no fake VALID. |
| AI validation? | Topology rules. AI geometry cannot self-certify. |
| City scale? | Architecture can tile; prototype is one block. |
| Legal today? | **No.** Exploration prototype for DoLR. |
| Standard? | LADM-**aligned**; CityGML export later; ULPIN parent per DoLR. |

---

## FINAL STACK

| Layer | Choice |
|---|---|
| Language | Python 3.11+ |
| API | FastAPI |
| DB | PostgreSQL 16 + PostGIS 3.5 + SFCGAL |
| Cloud | PDAL + Open3D |
| Vector 2D | Shapely / GEOS / GDAL |
| Front | React + CesiumJS (+ MapLibre 2D if needed) |
| IDs | UUID PK + `IN-ULPIN3D/…` display |
| Model | LADM-aligned spatial units + RRR |
| Demo CRS | EPSG:32643 (UTM 43N) |

**14-day build order:** Docker/PostGIS → schema → PDAL nDSM → footprint → floors/plans → extrude → utilities → topology tests → ULPIN API → Cesium happy path → slice/underground/errors → freeze demo.
