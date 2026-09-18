# SIH26011 — Master Research & Implementation Specification

**Project:** 3D ULPIN Generation and Vertical Property Mapping System  
**Problem ID:** SIH26011  
**Organisation:** Ministry of Rural Development — Department of Land Resources (DoLR)  
**Category / theme:** Software · Smart Automation  
**Official source:** [sih.gov.in/sih2026PS](https://www.sih.gov.in/sih2026PS) (verified 18 September 2026)  
**Document status:** Implementation-ready engineering specification  
**Rule:** This document separates **verified facts** from **our engineering proposal**. A proposed identifier is never called official ULPIN.

---

## 1. Executive summary

India already has a national surface-parcel identifier: **ULPIN / Bhu-Aadhaar**, a 14-character alphanumeric ID generated from geo-referenced parcel vertices under DILRMP. DoLR states that this unique ID “would spatially be pointing to the **surface** of the parcel.” That is why 2D ULPIN cannot uniquely identify a fifth-floor flat, a basement parking volume, an air-rights slab, or a sewer easement under the same plot.

**Fact:** No official Government of India 3D ULPIN standard was found in DoLR, DILRMP, or related public documentation as of 18 September 2026. SIH26011 is therefore an **open design problem**, not a request to implement a published 3D code format.

**Our 3D ULPIN is a proposed extension/representation compatible with the existing ULPIN concept.**

The product we will actually finish is **BhuvanRekha-3D** (working name: `ULPIN-3D`): a demonstrable 3D cadastral engine that:

1. Ingests a 2D cadastral polygon plus optional LiDAR/DSM, floor plans, and GNSS metadata.
2. Extracts or accepts a building footprint and height.
3. Segments floors and constructs **legal 3D spatial units** (apartment, common, parking, underground corridor).
4. Validates topology deterministically (not with a neural net).
5. Issues a **proposed 3D ULPIN** that always references the parent surface ULPIN.
6. Stores records in a **LADM-aligned** PostGIS model and visualises them in Cesium so a non-technical judge understands the story in 30 seconds.

**What we will not do:** train PointNet from scratch; claim government LiDAR we do not have; store CityGML as the system of record; encode full geometry inside the identifier; present AI geometry as legal title.

**Real novelty (defensible):** a **ULPIN-compatible vertical identity + legal-space engine** that separates physical geometry from rights, with deterministic topology validation and provenance. That combination is what international 3D cadastre research treats as the hard problem, and what Indian 2D ULPIN does not currently provide.

---

## 2. Problem interpretation

### 2.1 Official problem statement (verbatim structure)

Verified on the official SIH 2026 portal (`https://www.sih.gov.in/sih2026PS`) on 18 September 2026:

| Field | Value |
|---|---|
| PS Number | SIH26011 |
| Title | 3D ULPIN Generation and vertical Property Mapping SYstem |
| Organisation | Ministry of Rural Development |
| Department | Dept of land resources (DoLR) |
| Category | Software |
| Theme | Smart Automation |
| Idea deadline | 30 September 2026 |
| Submitted ideas (that date) | 15/500 |
| Dataset link | empty |
| YouTube / contact | empty |

**Background (official):** conventional 2D land-record systems cannot uniquely define ownership rights for multi-storey apartments, underground infrastructure, elevated transport corridors, parking spaces, air-rights, and subsurface utility networks.

**Required identities:** surface land parcels · multi-storey apartments · underground infrastructure.

**Required integrations:** drone imagery · LiDAR/3D point clouds · GIS parcel layers · building floor plans · GNSS/CORS coordinates · DEM/DSM.

**Named AI/ML capabilities:** automated building extraction · floor segmentation · vertical parcel delineation · intelligent topology validation.

**Expected outcome:** standardised 3D ULPINs · mapping of vertical and underground ownership rights · volumetric cadastre · urban property governance · fewer ownership conflicts · better infrastructure/utility planning.

**Important:** the portal provides **no dataset**. Any claim that “SIH gave us Indian LiDAR” is false.

### 2.2 What the problem is really asking

The shopping list is a **capability map**, not a mandate to build a national production cadastre in a hackathon. The scientifically honest reading:

1. **Identifier problem** — extend ULPIN from 2D surface lots to 3D legal spaces without breaking the existing 14-character parent.
2. **Geometry problem** — turn 2D footprints + heights + floor plans into closed volumetric parcels.
3. **Legal-space problem** — distinguish apartment units, common areas, parking, air rights, and utility corridors.
4. **Validation problem** — detect overlapping/gapped/invalid 3D parcels.
5. **Interop problem** — talk to GIS, GNSS, and (later) government land-record systems.

### 2.3 Problem class map (do not treat everything as AI)

| Capability | Class | MVP method |
|---|---|---|
| Surface parcel identification | Cadastral / geospatial | Ingest official polygon + official ULPIN if present |
| Multi-storey apartment ID | Cadastral + geometric | Floor-plan extrusion into legal units |
| Underground mapping | Geospatial + geometric | Centerline + buffer solid |
| 3D ULPIN generation | Identifier design | Hierarchical proposed ID; UUID persistence |
| Drone imagery | Computer vision / photogrammetry | Optional orthomosaic; not required for core path |
| LiDAR / point cloud | Geospatial + geometry | PDAL + Open3D classical extraction |
| GIS parcel layer | Geospatial | GeoJSON/shapefile → PostGIS |
| Floor plans | Geometric + cadastral | Digitised polygons / GeoJSON; IFC later |
| GNSS/CORS | Geospatial | CRS metadata + accuracy class; not a live CORS client |
| DEM/DSM | Geospatial | nDSM = DSM − DTM for height |
| Building extraction | Geometry (+ optional ML later) | CSF + nDSM + planarity |
| Floor segmentation | Geometry + fusion | Z-histogram + RANSAC + plan overlay |
| Vertical parcel delineation | Geometric | Extrude polygon to `[zmin, zmax]` solid |
| Topology validation | Deterministic geometry | PostGIS/SFCGAL/Shapely — **not ML** |
| Volumetric cadastre | Data model | LADM-aligned spatial units |
| Ownership ambiguity reduction | Legal data model | RRR tables; common-area as shared right |
| Utility planning | Geospatial | Underground spatial units + conflict checks |

**Rejected interpretation:** “we must ship a trained deep-learning stack for every named AI item.” Topology validation is a computational-geometry problem. Vertical delineation is extrusion + solid construction. Building extraction and floor detection can be classical for MVP and still satisfy the PS if we expose them as automated processing stages with confidence scores.

### 2.4 Indian legal overlay we must respect (not copy foreign law)

India does **not** have a national 3D cadastre statute. What exists:

- **ULPIN** identifies the **land parcel**, not the apartment.
- **State Apartment Ownership Acts** (e.g. Karnataka 1972, Punjab 1995, Tamil Nadu 2022) treat an apartment plus an **undivided share of common areas** as heritable immovable property. Common areas cannot be partitioned from the apartment.
- **RERA 2016 s.17** requires conveyance of the apartment to the allottee and undivided proportionate title in common areas to the association of allottees.

**Transferable international concepts (technical, not legal copy):**

| Concept | Source | Use in India prototype |
|---|---|---|
| Legal space ≠ physical building | FIG 3D Cadastres Best Practices; ISO 19152 | Separate `spatial_unit` from `building` mesh |
| Building-format vs volumetric-format lots | Queensland Land Title Act / Registrar Directions | Apartments = building-bounded; utilities/tunnels = volumetric |
| 3D PDF / 3D certificate as first operational step | Netherlands Kadaster (Delft 2016); Shenzhen 3D certificates | Demo “cadastral record card”, not a legal title |
| Strata / airspace / subterranean lots | Singapore SLA | Types we model: UNIT, COMMON, AIR, SUBSURFACE |
| Undivided common property | Indian apartment acts + RERA | `COMMON` spatial unit + shared RRR, not fake exclusive titles |

**Not transferable:** Queensland’s statutory volumetric plan rules; Dutch deed law; China’s 3D land-use right certificates. We model **spaces and rights**, we do not issue Indian titles.

---

## 3. Existing ULPIN research (facts)

### 3.1 What ULPIN is

DoLR official page *Bhu-Aadhar : Unique Land Parcel Identification Number (ULPIN)* ([dolr.gov.in/en/ulpin/](https://dolr.gov.in/en/ulpin/), last updated 25 April 2024):

> Unique Land Parcel Identification Number (ULPIN) is part of DILRMP. It is a **14-digit identification number** accorded to a land parcel based on the **longitude and latitude coordinates** of the land parcel and depends on detailed surveys and geo-referenced cadastral maps.

It is described as a “Single, Authoritative Source of Truth” for a parcel, intended to support integrated land services. DoLR says the system complies with **ECCMA** and **OGC** standards.

DILRMP guidelines PDF (DoLR, April 2024) repeats: ULPIN is for generating and assigning **14 digits — alphanumeric unique ID** for each land parcel based on **geo-coordinates of vertices**.

### 3.2 How it is generated (what is public)

DoLR generation notes:

1. There is a formula to generate ECCMA-prescribed 14-digit Unique ID **Property Natural Identifier Unit (PNIU)** using the parcel’s geo-referenced **vertices**.
2. This ID is organically dependent on parcel vertices in lat/long as **Property Natural Identifier Lot (PNIL)**, and the Unique ID (PNIU) would **spatially be pointing to the surface of the parcel**.

A 16 January 2020 DoLR presentation (circulated copies, e.g. MediaNama archive of *UNIQUE LAND PARCEL IDENTIFICATION NUMBER (ULPIN)*) adds:

- Implementation via webservice: **input = parcel geometry + EPSG code; output = PNIU, PNIL**.
- NIC / Survey of India / DST / NRSC to provide technical support.
- Some states historically used **different** local codes (AP random state-prefixed codes; UP 16-digit village+khasra codes). ULPIN is meant to standardise over those.

**Uncertainty (flagged):** the exact public algorithm that maps a vertex ring to the 14-character ULPIN is **not published as open source**. We will **ingest** an official ULPIN when provided. We will **not** claim that a hash we invent is a government-issued ULPIN.

### 3.3 ECCMA / ISO relationship (important and easy to get wrong)

ECCMA’s natural-location work is now reflected in **ISO 8000-118:2025** (Natural Location Identifiers). Public summaries of that standard (and ECCMA’s eNLI site) describe a reversible encoding of **WGS84 latitude, longitude, and storey or elevation** into a compact alphanumeric string (14 characters with storey, 15 with elevation). PNIU was originally described as applying a reversible algorithm to the **position and elevation of the midpoint of the plane representing the primary point of entry** to a legally delineated unit space.

That means:

- ECCMA/ISO NLI is a **point-based location code** (entrance / coordinate + floor).
- DoLR ULPIN, as implemented, is described as a **surface-parcel** ID derived from **vertices**, pointing at the **surface**.
- A floor-encoded NLI is **not** a volumetric cadastral parcel ID. Two flats can share an entrance corridor. A sewer has no “storey”. A parcel mutation changes vertices and therefore can change a geometry-derived ID.

**Decision:** use ISO 8000-118-style NLI, if implemented, only as an optional **location index**, never as the cadastral 3D ULPIN.

### 3.4 Coverage and ownership

- Rolled out in **29 States/UTs** (DoLR list includes AP, Jharkhand, Goa, Bihar, Odisha, Sikkim, Gujarat, Maharashtra, Rajasthan, Haryana, Tripura, Chhattisgarh, J&K, Assam, MP, Nagaland, Mizoram, Tamil Nadu, Punjab, DNH&DD, HP, West Bengal, UP, Uttarakhand, Kerala, Ladakh, Chandigarh, Karnataka, NCT of Delhi).
- Pilot in 4: Puducherry, Telangana, Manipur, A&N.
- Some states use ULPIN inside **SVAMITVA**.
- DoLR says ULPIN **may include** ownership details besides size and lat/long. Ownership is **linked**, not encoded as the ID itself. The ID is a key; RoR remains the rights register.

### 3.5 Does official 3D ULPIN exist?

**No public official 3D ULPIN standard was found.** Searches of DoLR ULPIN pages, DILRMP guidelines, National Geospatial Policy 2022, and Survey of India CORS/geodetic pages did not yield a 3D ULPIN schema, 3D PNIU profile, or gazette notification for vertical identifiers.

National Geospatial Policy 2022 (DST notification S.O. 6095(E), 28 December 2022) **does** list Land Parcels as a National Fundamental Geospatial Data Theme (DoLR rural / MoHUA urban) and calls for a strategy to map **subsurface infrastructure in cities in 3D**. That is policy intent, not a 3D ULPIN spec.

**Conclusion:** 3D ULPIN is currently an **open design problem**. SIH26011 is the DoLR asking teams to propose a workable extension.

### 3.6 Compatibility rule we will implement

```
Official surface ULPIN (14-char, if known)
        │
        ├── proposed 3D ULPIN for building envelope
        ├── proposed 3D ULPIN for floor slab (optional)
        ├── proposed 3D ULPIN for unit / common / parking
        └── proposed 3D ULPIN for underground / airspace volumes
```

Compatibility means:

1. Never overwrite or “improve” an official 14-character ULPIN.
2. Every 3D unit stores `parent_ulpin` (official or `UNKNOWN` + proposed surface key).
3. Geometry lives in the database, not inside the identifier.
4. Display strings are clearly labelled **PROPOSED**.

---

## 4. 3D cadastre research

### 4.1 Core definition

A 3D cadastre registers **rights, restrictions and responsibilities (RRR)** against **3D spatial units** (legal spaces), not merely against a 2D polygon. FIG *Best Practices 3D Cadastres* emphasises that the object of registration is the **legal space**, which may coincide with, sit inside, or cut through physical buildings and terrain.

### 4.2 Jurisdiction comparison (what to steal technically)

| Jurisdiction | Status | Useful idea | Do not copy |
|---|---|---|---|
| **Netherlands** | Operational 3D visualisation in deeds (Delft railway station, 2016); full 3D parcel DB still evolving | BIM → legal volume → registrable 3D view; start inside existing legal frames | Dutch deed law |
| **Queensland, AU** | Building Format Plans (walls/floors/ceilings) and Volumetric Format Plans (3D-located bounding surfaces) | Two geometry families: apartment vs tunnel/utility | Land Title Act procedures |
| **Singapore** | Strata, airspace, subterranean lots exist; many plans still 2D with heights | Lot types we need; coordinated cadastre | SLA survey regulations |
| **Shenzhen, CN** | Long-running 3D cadastre practice; 2025 3D real-estate certificate (Qianhai fire station) | 3D certificate + QR to 3D model; topology checks in land supply | Chinese land-use right system |
| **Spain / others** | Apartment 3D solutions | Unit-level visualisation | Not a full multi-level cadastre |

### 4.3 Indian apartment / common / parking / air / underground

For the prototype we adopt **legal-space types**, mapped to Indian practice in comments, not as a claim of statutory 3D lots:

| `su_class` | Meaning | Typical Indian analogue |
|---|---|---|
| `PARCEL` | Surface cadastral lot | ULPIN parcel / survey number |
| `BUILDING` | Physical envelope (not a title) | Structure on the parcel |
| `FLOOR` | Storey slab (administrative) | Floor in sanctioned plan |
| `UNIT` | Exclusive apartment/office | Apartment under state AOA + RERA |
| `COMMON` | Corridor, lift, stair, lobby | Undivided common areas → association |
| `PARKING` | Exclusive or limited-common parking | Deed / RERA allotment |
| `BALCONY` | Private or limited-common projection | Per sanctioned plan |
| `AIR` | Volume above a defined height | Air rights (rarely titled today) |
| `SUBSURFACE` | Underground parking / cellar | Basement as part of building or separate |
| `UTILITY` | Pipe/cable/tunnel corridor | Easement / utility ROW (often not cadastral) |

**Mandatory split:** `geom_physical` (walls, pipes, DSM) vs `geom_legal` (the space the right applies to). A wall is physical; the median plane or interior face used as a boundary is a legal-space modelling choice. MVP uses **interior of floor-plan polygons extruded between storey z-values** as legal space. We do **not** model wall-thickness ownership in MVP (FIG notes this is jurisdiction-specific and often undefined even in 2D drawings).

---

## 5. LADM research

### 5.1 What the standard is now

ISO 19152 LADM Edition I (2012) is superseded in parts by Edition II:

- **ISO 19152-1:2024** — generic conceptual model (Party, Admin, Spatial)
- **ISO 19152-2:2025** — land registration, including `LA_LegalSpaceBuildingUnit`, `LA_LegalSpaceUtilityNetworkElement`, `LA_LegalSpaceCivilEngineeringElement`, 2D/3D/mixed spatial units, survey sources including point clouds and GNSS
- Also published: valuation (part 4) and spatial plan (part 5)

LADM is explicitly a **descriptive conceptual model**, not a data-product specification. Full “LADM-conformant” claims require an abstract test suite we will not run in SIH.

### 5.2 Decision

| Option | Verdict |
|---|---|
| Custom ad-hoc tables only | Reject — untranslatable to DoLR/ISO language |
| Strict LADM-conformant | Reject — overkill; we are not a national LA system |
| **LADM-aligned** | **Accept** — our tables map 1:1 onto LADM classes; we do not implement every association |

**Mapping**

| Our table | LADM concept |
|---|---|
| `party` | `LA_Party` |
| `baunit` | `LA_BAUnit` |
| `rrr` | `LA_Right` / `LA_Restriction` / `LA_Responsibility` |
| `spatial_unit` | `LA_SpatialUnit` + legal-space subtypes |
| `building` / `floor` | physical references (`ExtPhysicalBuildingUnit` analogue) |
| `source_dataset` / `survey` | `LA_SpatialSource` / `LA_SurveySource` |
| `version` columns | `VersionedObject` |
| `ulpin_id` | external identifier |

**Reason:** judges from DoLR can be answered with “ISO 19152-2:2025 aligned, not a certified LADM product.” That is accurate.

---

## 6. CityGML / 3D city model research

CityGML 3.0 (OGC 20-010, 2021) is a **physical** 3D city model: Building, Construction, Tunnel, Relief, PointCloud, Transportation, etc. LOD 0–3. Utility networks are **not** a core 3.0 module; they live in Utility Network ADE.

CityGML does **not** model RRR. Linking CityGML buildings to LADM legal spaces is a known research pattern (e.g. TestbedLU IFC–CityGML–LADM FME workbenches; many FIG papers).

### Decision

| Layer | Format |
|---|---|
| **Internal store** | PostGIS 2D polygons + 3D solids + attributes (LADM-aligned) |
| **Visualisation** | Cesium entities / glTF / 3D Tiles (runtime) |
| **Export (advanced)** | CityGML 3.0 Building LOD1 + optional Relief; GeoJSON; glTF |
| **Not used internally** | Full CityGML database (3DCityDB) — too heavy for SIH |

CityGML is an **interoperability export**, not the system of record.

---

## 7. Data sources (honest)

Official SIH dataset field is **empty**. Do not invent Indian government dumps.

### 7.1 What exists in India (and what we can actually get)

| Source | What it is | SIH availability | Use |
|---|---|---|---|
| **CartoDEM** (NRSC/Bhuvan) | IRS DEM, ~1 arc-sec (~30 m); vertical accuracy ~8 m (90%) | Free download with daily tile limits | Terrain context only. **Too coarse for floors.** |
| **SVAMITVA drone/LiDAR** | High-res village abadi mapping | Scheme-held; not an open national LAS dump | Cite as production future source; **not our demo file** |
| **SoI CORS** | RTK/NRTK, RINEX; ITRF2008 epoch 2005 processing (independent of NSRF GCP network — flagged inconsistency in Current Science 2024/2025 papers) | Registration required; not needed live | CRS/accuracy metadata in the data model |
| **TALD** (IEEE Access 2025) | 9 km² Thiruvananthapuram ALS, ~12 pts/m², UTM 43N, classified buildings/trees/ground | Paper exists; download not confirmed as frictionless | **Optional** if we obtain it legally; otherwise do not claim we have it |
| **Official cadastral polygons** | State Bhu-Naksha / DILRMP | Not openly bulk-downloadable for a random city block | Ingest format yes; live state GIS no |
| **OSM buildings** | Crowd footprints | Yes | Rough physical footprints; **not legal parcels** |
| **Microsoft / Google building footprints** | Derived polygons | Possible with licence check | Physical only |

### 7.2 MVP dataset strategy (scientifically honest)

**Primary demo dataset (we will author):** `demo/pune_kothrud_block/` — a **synthetic but georeferenced** 1-parcel / 1-building scene placed in a real Indian urban CRS (EPSG:32643, UTM 43N) with:

- 1 cadastral polygon (~800–1500 m²) with a **placeholder 14-char parent ULPIN** labelled `OFFICIAL_ULPIN_PLACEHOLDER` or ingested string.
- 1 G+4 or G+7 apartment building.
- Floor-plan GeoJSON for 2 representative floors (repeated with translation in Z).
- Synthetic airborne-style LAS (building + ground + trees) **or** a public non-Indian cloud used only for the extraction algorithm, clearly labelled.
- 1 underground water line + 1 sewer line as 3D polylines.
- 1 deliberately invalid overlapping unit for the validation demo.

**Secondary algorithm benchmarks (labelled non-cadastral):**

- ISPRS Vaihingen 3D / similar open ALS for building-extraction metrics.
- Public raster floor-plan samples for vectorisation experiments (not Indian legal plans).

**Rejected false claims:** “we will use SVAMITVA LiDAR for Pune”; “Bhuvan 30 m DEM gives floor heights”; “we have DoLR parcel APIs.”

### 7.3 CRS policy

| Role | CRS |
|---|---|
| Storage / geometry engine | Projected metres, UTM zone of the site (demo: EPSG:32643) + ellipsoidal or orthometric Z documented per dataset |
| Identifier / display | WGS84 lon/lat (EPSG:4326) for parent ULPIN compatibility |
| Cesium | WGS84 / ECEF via runtime transform |
| Heights | Store `z_ref` enum: `ELLIPSOIDAL_WGS84` \| `ORTHOMETRIC_EGM` \| `LOCAL_SITE` |

CORS/GNSS: we store reported horizontal/vertical accuracy and EPSG. We do **not** build a live NRTK client in MVP.

---

## 8. Data fusion pipeline

Default CRS: site UTM (metres). All stages log `run_id`, `processor_version`, confidence, and failure code.

| # | Stage | Input | Output | Algorithm | Library | Accuracy target (MVP) | Failure | Fallback |
|---|---|---|---|---|---|---|---|---|
| 0 | Ingest | files + metadata | `source_dataset` rows | checksum, MIME, CRS read | GDAL/PDAL | n/a | unreadable file | reject with error |
| 1 | CRS normalize | mixed EPSG | all in site CRS | `pyproj` / GDAL warp | GDAL, pyproj | reprojection error ≪ survey error | missing CRS | **hard fail** (never guess silently) |
| 2 | Quality | clouds, rasters, polygons | QA report | density, nodata, ring validity | PDAL, Shapely | density ≥ 4 pts/m² preferred | empty/corrupt | continue with degraded confidence |
| 3 | Parcel align | cadastral polygon | `spatial_unit` PARCEL | make valid, force 2D | Shapely/PostGIS | topology valid | self-intersect | `ST_MakeValid` + flag |
| 4 | DTM/DSM | LAS or rasters | DTM, DSM, nDSM | CSF or vendor classes; rasterize | PDAL CSF, rasterio | DTM ±0.3–1 m if dense ALS | no ground class | morphological filter / provided DTM |
| 5 | Building extract | nDSM + cloud | footprint polygon | height threshold + planarity + morph | PDAL, Open3D, SciPy | IoU ≥ 0.7 vs reference footprint | vegetation confusion | OSM/manual footprint |
| 6 | Height | building points / nDSM | `z_ground`, `z_roof` | percentiles (p5 ground, p95 roof) | NumPy | ±0.5–1.5 m typical ALS | too few points | metadata storeys × 3.0 m |
| 7 | Floor segment | height + optional indoor cloud + plans | `z` bands per storey | Z-histogram peaks; RANSAC planes; plan priority | Open3D, NumPy | ±0.3 m if plans; ±0.5–1.0 m if height-only | no peaks | equal slice `H / N_storeys` |
| 8 | Plan integrate | GeoJSON/IFC spaces | unit polygons in site CRS | Helmert/affine georeference | Shapely | RMSE_xy ≤ 0.5 m if GCPs | no plan | whole-floor as one UNIT + COMMON unknown |
| 9 | Vertical construct | footprint/unit poly + zmin/zmax | `POLYHEDRALSURFACE Z` solid | `CG_Extrude` / prism builder | PostGIS SFCGAL | closed solid | non-simple poly | simplify then extrude |
| 10 | Underground | 3D lines + diameter | corridor solid | sweep/buffer in XY + Z slab or cylinder approx | Shapely 3D prism | schematic, not survey | missing Z | default cover depth 1.2–2.5 m **flagged** |
| 11 | Topology | all solids | `validation_result` | see §15 | PostGIS, SFCGAL, Shapely | 100% rule coverage on demo | overlapping units | block “validated” status |
| 12 | 3D ULPIN | valid spatial unit | display ID + UUID | see §11 | Python | unique in DB | missing parent | parent = proposed surface key |
| 13 | Persist | objects | rows | SQLAlchemy | PostgreSQL | ACID | constraint fail | transaction rollback |
| 14 | Serve | DB | JSON + glTF | REST | FastAPI | < 2 s hot demo | — | — |
| 15 | Visualise | entities | globe | 3D extrusion + underground translucency | CesiumJS | judge-readable | WebGL fail | 2D MapLibre fallback |

**Pipeline diagram**

```
[Parcel GeoJSON] [LAS/LAZ or DSM] [Floor-plan GeoJSON] [Utility GeoJSON] [GNSS/CRS meta]
        \              |                  |                    |                 /
         \             |                  |                    |                /
                    CRS normalize + QA  (hard-fail if CRS missing)
                                 |
                    DTM/DSM → nDSM → building footprint + height
                                 |
                    Floor bands (histogram/RANSAC) ⊕ floor-plan units
                                 |
              Extrude legal solids     Buffer underground corridors
                                 |
                    Deterministic topology validation
                                 |
                    Proposed 3D ULPIN  (parent = official 14-char ULPIN)
                                 |
                    PostGIS (LADM-aligned) → FastAPI → Cesium
```

---

## 9. AI / ML strategy

### 9.1 Building extraction comparison

| Method | Accuracy potential | Train data | Cost | SIH fit | Verdict |
|---|---|---|---|---|---|
| CSF + nDSM + morph + planarity | Good on ALS ≥ ~8–12 pts/m² | none | low | high | **Primary** |
| RANSAC roof planes (Open3D) | Good roofs, weak footprints alone | none | low | high | used inside primary |
| PointNet++ / KPConv / RandLA-Net | High on similar train domain | large labelled clouds | high GPU | poor for MVP | **Advanced only** |
| Image instance segmentation (buildings) | Needs nadir imagery + labels | high | medium | weak without Indian labels | rejected for MVP |
| Hybrid: classical propose, ML refine | best long-term | medium | medium | after MVP | future |

**Primary:** unsupervised ALS workflow (CSF ground filter → DSM/DTM → nDSM height mask → vegetation rejection by planarity/TRI → contour regularisation). This is the family used by open tools such as LasBuildSeg and multiple ISPRS building-mapping papers. No training set required.

**Fallback:** user-supplied or OSM footprint + height from DSM percentiles or `storeys × 3.0 m`.

**Rejected:** training PointNet on TALD during SIH; calling a random Hugging Face model “cadastral AI.”

### 9.2 Floor segmentation

Indoor LiDAR literature (e.g. storey histogram + RANSAC floors/ceilings) assumes **interior** point clouds. Airborne LiDAR usually sees **roof and ground**, not slabs. Therefore:

**MVP algorithm (hybrid, geometry-first):**

1. If floor-plan / BIM spaces exist: they **win** for unit boundaries. Z comes from plan metadata or `i × h_storey + z_ground`.
2. Else if interior cloud exists: Z-histogram (bin 5–10 cm) → peaks = slabs → RANSAC horizontal planes (`distance_threshold ≈ 0.15–0.30 m`).
3. Else (airborne only): `n_floors` from metadata **or** `round((z_roof − z_ground) / 3.0)` with `h_storey` default 3.0 m (NBC-typical residential; **flagged as assumed**).
4. Geometry validator: floors must be monotonic in Z, gap ∈ [2.4, 4.5] m unless metadata says otherwise, no overlap.

**ML** is not the proposer in MVP. If we add it later, it may propose `n_floors` from facade images; geometry still validates.

### 9.3 Topology

**100% deterministic.** No classifier. “Intelligent” in the PS is implemented as **rule-based spatial intelligence** (overlaps, containment, CRS, Z, parent-child), which is what cadastral systems actually use (Queensland eSurvey validation, Shenzhen 3D topology checks).

### 9.4 Presentation rule

Every automated geometry row has `geom_origin ∈ {SURVEY, PLAN, AI_DERIVED, SYNTHETIC, MANUAL}` and is **never** shown as “legal title.”

---

## 10. Geometry strategy

### 10.1 How a 2D polygon becomes a 3D parcel

Canonical construction:

```
legal_solid = Extrude(footprint_xy, zmin, zmax)
```

where `footprint_xy` is a simple polygon in site CRS and `[zmin, zmax]` is the vertical extent of that legal space.

### 10.2 Representation comparison

| Rep | Pros | Cons | Use |
|---|---|---|---|
| Voxel | easy occupancy | huge, non-legal | reject |
| Triangle mesh only | pretty | hard CSG/validity | viz only |
| CityGML solid | standard physical | poor RRR | export |
| IFC `IfcSpace` | BIM legal spaces | IFC stack heavy | advanced ingest |
| Multipatch | ESRI-centric | not our DB | reject |
| **POLYHEDRALSURFACE Z + SFCGAL solid** | native PostGIS CSG, volume, 3D intersection | prism assumption | **canonical legal geom** |
| 2D poly + `zmin/zmax` columns | trivial, fast 2.5D checks | not a true solid | **construction params** (always stored) |

**Decision:** store **both** `geom_2d` + `zmin/zmax` (fast parent/overlap in 2.5D) **and** `geom_3d` solid (volume, 3D intersection, demo mesh). Most apartments in India are vertical prisms; that matches Queensland “building format” more than arbitrary B-Rep. Non-vertical walls (rare in MVP) deferred.

Underground utilities: approximate as **horizontal prism / stadium-buffer extrusion** along centerline at given depth and diameter. True cylinder sweep is advanced.

Libraries: Shapely 2.x for 2D; PostGIS 3.5+ `CG_Extrude`, `CG_MakeSolid`, `CG_Volume`, `CG_3DIntersection` (SFCGAL). Open3D for point-cloud planes, not for cadastral solids.

---

## 11. 3D ULPIN design

### 11.1 Three candidates

**A — Geometry-encoded NLI (ISO 8000-118 / ECCMA PNIU-style)**  
Encode centroid + storey into ~14 chars.  
*Reject:* point, not volume; unstable if entrance moves; collisions; DoLR ULPIN already uses 14 chars for **surface** parcels; underground poorly represented.

**B — Opaque UUID only**  
Stable, easy.  
*Reject as display ID:* judges/DoLR cannot see relationship to official ULPIN. Keep UUID as **internal PK only**.

**C — Hierarchical proposed identifier + UUID persistence (SELECTED)**

```
Internal PK:     ulpin3d_uuid  (UUIDv7, immutable)

Display ID:      IN-ULPIN3D/{parent_ulpin}/{su_class}/{local_code}/v{nn}

Example:         IN-ULPIN3D/12AB34CD56EF78/UNIT/F05-U501/v01
```

| Part | Rule |
|---|---|
| `IN-ULPIN3D` | namespace; marks **proposed** extension |
| `parent_ulpin` | official 14-char if known; else `P{12-char fingerprint of WGS84 centroid}` labelled proposed |
| `su_class` | PARCEL\|BUILDING\|FLOOR\|UNIT\|COMMON\|PARKING\|AIR\|SUBSURFACE\|UTILITY |
| `local_code` | stable within parent, e.g. `F05-U501`, `UTL-WTR-01` |
| `vNN` | legal version, not geometry-tweak version |

Geometry hash (`sha256` of WKT) stored separately for change detection.

### 11.2 Lifecycle

| Event | ID behaviour |
|---|---|
| Geometry snap / QA fix | UUID **unchanged**; hash updates; version **unchanged**; provenance note |
| Floor modification (legal) | new version `vN+1`; old row `status=SUPERSEDED` |
| Subdivision | parent UUID remains; children get new UUIDs; `derived_from` links |
| Merger | new UUID; sources linked; old SUPERSEDED |
| Redevelopment / demolition | `status=EXTINGUISHED`; UUID never recycled |
| Duplicate prevention | unique `(parent_ulpin, su_class, local_code, version)` plus unique UUID |

**Uniqueness:** DB constraints. **Persistence:** UUID never reused. **Stability:** display local_code changes only on legal events.

---

## 12. Database schema

PostgreSQL 16 + PostGIS 3.5 + `postgis_sfcgal`.

```sql
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS postgis_sfcgal;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- enumerations
CREATE TYPE su_class AS ENUM (
  'PARCEL','BUILDING','FLOOR','UNIT','COMMON','PARKING',
  'BALCONY','AIR','SUBSURFACE','UTILITY'
);
CREATE TYPE geom_origin AS ENUM (
  'SURVEY','PLAN','AI_DERIVED','SYNTHETIC','MANUAL'
);
CREATE TYPE topology_status AS ENUM (
  'PENDING','VALID','INVALID','DEGRADED'
);
CREATE TYPE rrr_type AS ENUM (
  'RIGHT','RESTRICTION','RESPONSIBILITY'
);
CREATE TYPE object_status AS ENUM (
  'ACTIVE','SUPERSEDED','EXTINGUISHED'
);

CREATE TABLE source_dataset (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  kind          text NOT NULL, -- las, geojson, geotiff, ifc, csv
  filename      text NOT NULL,
  checksum_sha256 text NOT NULL,
  epsg          int,
  z_ref         text,
  acquired_at   timestamptz,
  ingested_at   timestamptz NOT NULL DEFAULT now(),
  meta          jsonb NOT NULL DEFAULT '{}'
);

CREATE TABLE survey (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  method        text, -- GNSS, CORS, photogrammetry, ALS, total_station, unknown
  h_rmse_m      numeric,
  v_rmse_m      numeric,
  source_id     uuid REFERENCES source_dataset(id)
);

CREATE TABLE party (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  party_type    text NOT NULL, -- person, org, association, authority
  name          text NOT NULL,
  ext_ref       text
);

CREATE TABLE baunit (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name          text,
  uid           text UNIQUE
);

CREATE TABLE spatial_unit (
  id              uuid PRIMARY KEY, -- ulpin3d_uuid
  parent_id       uuid REFERENCES spatial_unit(id),
  parent_ulpin    text,  -- official 14-char or proposed surface key
  su_class        su_class NOT NULL,
  local_code      text NOT NULL,
  version         int NOT NULL DEFAULT 1,
  display_id      text NOT NULL UNIQUE, -- IN-ULPIN3D/...
  status          object_status NOT NULL DEFAULT 'ACTIVE',
  geom_2d         geometry(Polygon, 32643) NOT NULL,
  zmin            double precision NOT NULL,
  zmax            double precision NOT NULL,
  geom_3d         geometry(PolyhedralSurfaceZ, 32643),
  volume_m3       double precision,
  geom_origin     geom_origin NOT NULL,
  confidence      numeric CHECK (confidence BETWEEN 0 AND 1),
  topology_status topology_status NOT NULL DEFAULT 'PENDING',
  geom_hash       text,
  baunit_id       uuid REFERENCES baunit(id),
  valid_from      timestamptz NOT NULL DEFAULT now(),
  valid_to        timestamptz,
  created_at      timestamptz NOT NULL DEFAULT now(),
  CHECK (zmax > zmin),
  UNIQUE (parent_ulpin, su_class, local_code, version)
);

CREATE INDEX su_gix_2d ON spatial_unit USING GIST (geom_2d);
CREATE INDEX su_gix_3d ON spatial_unit USING GIST (geom_3d gist_geometry_ops_nd);
CREATE INDEX su_parent ON spatial_unit (parent_id);
CREATE INDEX su_class_idx ON spatial_unit (su_class);

CREATE TABLE building (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  spatial_unit_id uuid UNIQUE REFERENCES spatial_unit(id),
  storeys_above   int,
  storeys_below   int,
  z_ground        double precision,
  z_roof          double precision,
  extraction_method text
);

CREATE TABLE floor (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  building_id     uuid REFERENCES building(id),
  spatial_unit_id uuid UNIQUE REFERENCES spatial_unit(id),
  level_index     int NOT NULL,
  label           text
);

CREATE TABLE rrr (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  baunit_id     uuid NOT NULL REFERENCES baunit(id),
  party_id      uuid NOT NULL REFERENCES party(id),
  spatial_unit_id uuid REFERENCES spatial_unit(id),
  rrr_type      rrr_type NOT NULL,
  share         numeric, -- undivided share 0-1 for COMMON
  description   text,
  UNIQUE (baunit_id, party_id, spatial_unit_id, rrr_type)
);

CREATE TABLE validation_result (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  spatial_unit_id uuid REFERENCES spatial_unit(id),
  run_id          uuid NOT NULL,
  rule_code       text NOT NULL,
  passed          boolean NOT NULL,
  severity        text NOT NULL, -- ERROR, WARN
  detail          jsonb,
  created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE process_run (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  stage           text NOT NULL,
  processor_ver   text NOT NULL,
  source_ids      uuid[] ,
  metrics         jsonb,
  started_at      timestamptz NOT NULL DEFAULT now(),
  finished_at     timestamptz
);
```

Versioning: legal change inserts a new `spatial_unit` row (new version or new UUID per §11.2); old row gets `status` + `valid_to`. No in-place overwrite of legal geometry without a provenance event.

---

## 13. API architecture

Base: ` /api/v1 `  JSON. Idempotent GETs. Processing endpoints return `run_id` and poll via `/runs/{id}`.

| Method | Path | Purpose |
|---|---|---|
| POST | `/datasets` | upload + CRS metadata |
| GET | `/datasets/{id}` | provenance |
| POST | `/sites` | create a processing site (CRS, bbox) |
| POST | `/sites/{id}/process` | run full pipeline or `?stage=` |
| GET | `/runs/{id}` | stage logs, metrics |
| GET | `/parcels/{id}` | surface parcel + children |
| GET | `/buildings/{id}` | envelope, storeys |
| GET | `/floors/{id}` | units on floor |
| GET | `/spatial-units/{id}` | full legal space + 3D ULPIN + confidence |
| GET | `/spatial-units/{id}/model.gltf` | mesh |
| GET | `/underground` | utility units in bbox |
| POST | `/validate` | topology run |
| GET | `/validation/{run_id}` | rule results |
| POST | `/ulpin3d/issue` | issue proposed IDs for validated units |
| GET | `/search?ulpin=` | parent or 3D ID lookup |
| GET | `/health` | db/sfcgal |

No public write of “official ULPIN.” Issuance always sets `namespace=IN-ULPIN3D` and `status=PROPOSED`.

---

## 14. Frontend architecture

**Choice: CesiumJS + React (Vite) + a 2D MapLibre overlay for the parcel table.**

| Option | Globe + CRS | Underground | 3D Tiles | SIH fit |
|---|---|---|---|---|
| **CesiumJS** | native WGS84 | translucency + collision off | native | **selected** |
| Three.js | DIY globe | DIY | extra loaders | rejected as primary |
| deck.gl | good overlays | weaker cadastral globe | Tile3DLayer | optional layer later |
| MapLibre | excellent 2D | poor 3D cadastre | limited | 2D companion |

**30-second judge UI (left → right):**

1. 2D parcel highlighted on globe.
2. Point cloud / DSM fades in.
3. Building extrusion appears.
4. Click floor → isolate slab.
5. Click Flat 501 → cyan legal volume + ID `IN-ULPIN3D/…/UNIT/F05-U501/v01`.
6. Slider slices Z; globe becomes translucent; sewer corridor appears.
7. “Validate” paints a red overlapping fake unit; “Fix” removes it.

Panels: Property card (ULPIN, parent ULPIN, class, zmin/zmax, volume, origin, confidence, topology). Never use the word “title granted.”

---

## 15. Validation (deterministic)

| Rule | Detects | Engine |
|---|---|---|
| `CRS_DEFINED` | missing/unknown EPSG | custom |
| `Z_RANGE` | zmax ≤ zmin, insane heights | SQL CHECK + Python |
| `SIMPLE_2D` | self-intersecting rings | Shapely / GEOS |
| `CLOSED_3D` | non-solid / not closed | SFCGAL `CG_IsSolid` / volume |
| `PARENT_CONTAIN` | unit footprint not in parcel | `ST_CoveredBy` (2D) |
| `UNIT_OVERLAP` | 3D intersection volume > ε | `CG_3DIntersection` + `CG_Volume` |
| `FLOOR_GAP` | storey gaps outside tolerance | custom Z |
| `FLOOR_OVERLAP` | overlapping Z bands | custom Z |
| `FLOATING` | unit not stacked on building Z | custom |
| `DUPLICATE_VOL` | geom_hash collision different ID | SQL |
| `DISCONNECTED` | MultiPolygon parts without flag | Shapely |
| `BLDG_PARCEL` | building footprint outside lot | PostGIS |
| `UTIL_SURFACE` | utility intersecting UNIT volume | SFCGAL (WARN unless easement) |
| `ID_UNIQUE` | display_id / business key | unique indexes |

ε for volumetric overlap: **0.01 m³** on demo solids (avoid numerical noise).

Invalid geometry **cannot** receive `topology_status=VALID` and should not be shown as a clean cadastral card in the happy-path demo.

---

## 16. Evaluation

**What we can honestly measure in SIH**

| Metric | How | Realistic target on demo |
|---|---|---|
| Building footprint IoU | vs hand digitised roof | ≥ 0.70 if using our synthetic/open ALS |
| Floor count accuracy | vs metadata | 100% on happy path with plans |
| Storey elevation MAE | vs plan | ≤ 0.3 m with plans; ≤ 1.0 m height-only |
| Overlap rule precision/recall | seeded errors | 100% on injected overlaps |
| Horizontal RMSE of plan georef | GCPs | ≤ 0.5 m |
| Pipeline time one building | wall clock | < 60 s excluding huge LAS |
| Peak RAM | one tile | < 8 GB |

City-scale FPS and national RoR integration are **out of scope** as claims. We can discuss architecture scaling (tiling, 3D Tiles) without fake numbers.

Hausdorff distance: optional on footprints if we have a reference polygon; skip if we only have synthetic truth we ourselves created (still useful as regression test).

---

## 17. Benchmark / test cases

| Case | Data | Must prove |
|---|---|---|
| **N1 Normal** | G+4 regular, complete plans, clean LAS | full path to 3D ULPIN |
| **D1 Difficult** | L-shaped building, noisy cloud, missing 1 floor plan | degraded confidence, not crash |
| **U1 Underground** | water + sewer vs basement | corridor solids + WARN if clash |
| **F1 Fail CRS** | shapefile without EPSG | hard fail, clear error |
| **F2 Fail overlap** | two units same volume | INVALID + red viz |
| **F3 Fail LiDAR** | parcel + plans only | height-from-metadata path |
| **F4 Fail plans** | parcel + LAS only | whole-floor units, COMMON unknown |

Each pipeline stage has a pytest using these fixtures.

---

## 18. MVP vs advanced vs not-in-SIH

### MVP (must work end-to-end)

- 1 Indian-CRS demo site, 1 parcel, 1 building, ≥ 4 storeys, ≥ 2 units/floor, 1 corridor COMMON, 1 parking, 1 underground utility.
- Ingest GeoJSON + LAS/LAZ or DSM + floor-plan GeoJSON.
- Classical building extraction **or** fallback footprint.
- Floor bands + extrusion to solids.
- Proposed 3D ULPIN with parent 14-char field.
- Topology validation + injected error demo.
- Cesium 2D/3D, floor isolate, Z-slice, underground toggle, provenance card.
- LADM-aligned PostGIS + FastAPI.

### Advanced (time permitting)

- IFC `IfcSpace` ingest.
- CityGML LOD1 export.
- RandLA-Net optional building class (off by default).
- Facade-based storey count.
- 3D Tiles for larger tiles.
- Multiple buildings in one block.
- ISO 8000-118 NLI as secondary location index.

### Do not attempt in SIH

- National ULPIN webservice reverse-engineering presented as official.
- Live CORS streaming.
- Conclusive titling / legally binding certificates.
- Full IndoorGML navigation graphs.
- Training foundation 3D models.
- Real SVAMITVA/DILRMP bulk data scraping.
- Wall-thickness legal boundary debates as a product feature.
- City-wide production cadastre.

---

## 19. Demo strategy

**Scene:** “Sinhagad Road, Pune — one redeveloped residential parcel” (synthetic data, real CRS). Spoken line: *Official ULPIN names the land. We name the volume.*

**Script (≤ 4 minutes)**

1. Show 2D parcel + 14-char parent ULPIN.
2. Load point cloud / DSM.
3. Run extract → footprint + LOD1 extrusion.
4. Detect floors (histogram + 3.0 m check) → overlay plans for floor 5.
5. Click Flat 501 → legal solid + `IN-ULPIN3D/…/UNIT/F05-U501/v01`.
6. Show COMMON corridor as **association undivided share**, not a fake private title.
7. Vertical slice.
8. Toggle underground water main (easement WARN if it clips basement).
9. Load corrupted duplicate unit → validation FAIL (red).
10. Reprocess → VALID cadastral card with confidence 0.86 PLAN+SURVEY, not “AI legal truth.”

---

## 20. Risks

| # | Risk | Mitigation |
|---|---|---|
| 1 | No official Indian LAS/parcels | Synthetic georeferenced demo + honest labelling |
| 2 | Airborne LiDAR cannot see floors | Plans-first Z; height heuristics flagged |
| 3 | Judges think we invented official ULPIN | Banner: PROPOSED extension; parent field immutable |
| 4 | SFCGAL solids fail on dirty polygons | `ST_MakeValid`, simplify, store 2.5D params always |
| 5 | Deep-learning rabbit hole | Classical pipeline frozen as MVP |
| 6 | CRS silent error | Hard-fail missing EPSG |
| 7 | Cesium underground camera | translucency + disable collision; 2D fallback |
| 8 | Over-scoped data model | One site, one building |
| 9 | Legal overclaim | geom_origin + “not a title” copy |
| 10 | ID instability | UUID PK; version on legal events only |

---

## 21. Judge questions (evidence-backed short answers)

**Why can’t existing ULPIN solve this?**  
DoLR: PNIU “spatially pointing to the **surface** of the parcel.” One ID for the lot cannot distinguish Flat 501 from the sewer under it.

**Why 3D?**  
Vertical cities create overlapping RRRs on the same X,Y. FIG and ISO 19152-2 exist because 2D projection is ambiguous. India NGP 2022 also asks for 3D subsurface mapping.

**Why not just a building ID?**  
A building is physical. Cadastre needs **legal spaces** (units, common, easements) with parties and shares. LADM separates those.

**How is 3D ULPIN related to official ULPIN?**  
It is a **proposed extension**. Display IDs nest under the official 14-character parent. We do not mint government ULPIN.

**Who owns common areas?**  
RERA s.17 + state apartment acts: undivided proportionate share, typically to the association; not partitioned. We model `COMMON` + shared RRR.

**Underground rights?**  
`UTILITY` / `SUBSURFACE` spatial units; default RRR type RESTRICTION/easement unless a party is assigned. MVP is geometric + data-model, not a new statute.

**Accuracy?**  
Report measured demo metrics, not national cm claims. Plans path ~0.3 m Z; ALS footprint IoU target ≥ 0.7; 30 m CartoDEM is not used for floors.

**LiDAR missing?**  
Fallback: footprint + storey metadata / equal slice. Confidence drops; origin ≠ SURVEY.

**Floor plans missing?**  
Whole-floor prisms; unit subdivision skipped; status DEGRADED.

**Validate AI?**  
AI/classical geometry never auto-VALID. Topology rules + human/plan source beat model scores.

**Scale to a city?**  
Architecture (tiles, PostGIS, 3D Tiles) can; this prototype is one block. Do not claim city production.

**Government GIS?**  
Ingest shapefile/GeoJSON + EPSG. Export GeoJSON/CityGML LOD1. No fake Bhu-Naksha login.

**Standard?**  
LADM-aligned ISO 19152-2:2025; OGC CityGML export optional; ULPIN parent per DoLR.

**Export geometry?**  
Yes: WKT/WKB, glTF, GeoJSON footprint, optional CityGML.

**Building modified?**  
New version or new units; old UUID extinguished/superseded; parent ULPIN remains until parcel mutation.

**Subdivision/merger?**  
New UUIDs, `derived_from`, versions; never recycle IDs.

**Duplicate IDs?**  
Unique indexes on UUID and business key.

**Legally usable immediately?**  
**No.** Prototype for DoLR exploration. Not a conclusive title system.

**Prototype vs production?**  
Prototype: one site, proposed IDs, synthetic/open data. Production would need official ULPIN API, survey-grade control, statute, and operational GIS.

---

## 22. Technology decision matrix

| Area | Options | Choice | Why | Rejected because |
|---|---|---|---|---|
| Point cloud IO/filters | PDAL vs Open3D-only | **PDAL + Open3D** | PDAL for LAS/LAZ/CSF pipelines; Open3D for RANSAC/normals | PDAL-only weak interactive geometry; Open3D-only weak production LAS pipelines |
| GIS DB | PostGIS vs SpatiaLite vs Mongo | **PostGIS+SFCGAL** | 3D solids, SQL validation, government-familiar | SpatiaLite weak 3D CSG; document DBs poor topology |
| Viz | Cesium vs Three vs deck | **CesiumJS** | globe, underground, WGS84 | Three = DIY geospatial; deck = overlay library |
| Legal geom | SFCGAL vs mesh vs voxel | **SFCGAL solids + 2.5D params** | volume & intersection | voxels unlegal; mesh-only hard to validate |
| Building extract | classical vs DL vs hybrid | **classical; DL later** | no labels, explainable | DL needs TALD-scale training we may not have |
| Floors | RANSAC vs ML vs plans | **plans ⊕ histogram/RANSAC** | airborne LiDAR lacks slabs | ML storey counting unreliable without facades |
| Data model | custom vs aligned vs conformant | **LADM-aligned** | speak ISO without fake certification | full conformance untestable in SIH |
| City model | CityGML core vs ADE vs none | **export LOD1 only** | avoid 3DCityDB weight | forcing CityGML internally mixes physical/legal |

---

## 23. What others are doing — and our gap

Already solved in literature/open source:

- ALS building footprints (many ISPRS pipelines; LasBuildSeg).
- Floor histogram + RANSAC (indoor reconstruction papers).
- LADM+Cesium apartment viewers (e.g. PointCloud3DLAS / Andinasari 2025: Rotterdam floor plans + AHN + PostgreSQL + Cesium).
- Netherlands BIM-to-3D-deed visualisation.
- Shenzhen 3D certificates.

Still weak / missing for **India + ULPIN**:

- Binding 3D units to **official 14-char ULPIN** as parent (almost nobody does this).
- Modelling **RERA/association common areas** rather than European condominium clones.
- Honest **no-LiDAR / no-plan** degradations with provenance.
- Deterministic topology as a first-class demo, not a hidden SQL check.
- Explicit **proposed vs official** identifier hygiene (other SIH teams are likely to mint a new “ULPIN” and overclaim).

**Differentiators we will actually ship:**

1. ULPIN-compatible hierarchical proposed 3D ID (parent never overwritten).
2. Legal-space vs physical-geometry split with Indian common-area RRR.
3. Prism solid engine + SFCGAL topology with injected-error demo.
4. Provenance/confidence on every volume.
5. Plans-first floor logic (correct for airborne Indian data realities).

---

## 24. Final decisions (no “both are possible”)

### Architecture
**Decision:** Python FastAPI processing services + PostgreSQL/PostGIS/SFCGAL + React/Cesium client.  
**Reason:** one language for PDAL/Open3D/Shapely; SQL for topology; Cesium for globe/underground.  
**Evidence:** same pattern as recent 3D LAS academic prototypes; PostGIS SFCGAL docs for `CG_Extrude` / `CG_3DIntersection`.  
**Rejected:** Django-monolith, Node geometry, 3DCityDB-first, Unity demo.  
**Consequence:** team must install PostGIS with SFCGAL; Windows: use WSL or Postgres.app-equivalent installer carefully.

### Data model
**Decision:** LADM-aligned schema in §12.  
**Rejected:** full ISO conformance; purely custom GIS layers.

### 3D ULPIN
**Decision:** Candidate C — UUID + `IN-ULPIN3D/{parent}/{class}/{local}/vNN`.  
**Rejected:** ISO 8000-118 as cadastral ID; UUID-only display.

### AI/ML
**Decision:** classical extract + geometric floors; ML optional later. Topology not ML.

### Geometry
**Decision:** 2D footprint + z-range + SFCGAL solid prisms.

### Frontend
**Decision:** CesiumJS primary.

### Standards
**Decision:** DoLR ULPIN as parent key; ISO 19152-2 aligned; CityGML export optional; OGC GeoJSON/glTF on the wire.

### Datasets
**Decision:** authored synthetic Indian-CRS demo + optional public ALS for metrics; no fake SVAMITVA dump.

### MVP / demo / metrics
As §§16–19.

---

## 25. Development order

Assume 14 focused days after this spec (adjust to team calendar).

| Day | Outcome |
|---|---|
| 1 | Repo, Docker Compose (Postgres+PostGIS), CRS utilities, `demo/` GeoJSON parcel |
| 2 | Schema migration, seed PARCEL + placeholder parent ULPIN |
| 3 | PDAL pipeline: read LAS, CSF, nDSM GeoTIFF |
| 4 | Building footprint extract + fallback OSM/manual |
| 5 | Height + floor-band detector + unit GeoJSON ingest |
| 6 | Extrude solids in PostGIS; volume; glTF export |
| 7 | Underground buffer solids |
| 8 | Topology rules + pytest fixtures (N1, F2, F1) |
| 9 | 3D ULPIN issuer + API GETs |
| 10 | Cesium globe: parcel, building, click unit |
| 11 | Floor isolate, Z-slider, underground, validation colours |
| 12 | Provenance card, confidence, injected-error demo polish |
| 13 | Metrics notebook, README, judge Q&A dry run |
| 14 | Freeze demo data; record backup video; bug buffer |

---

## 26. References

### Tier 1 — Government / standards

1. Smart India Hackathon, SIH26011 listing, `https://www.sih.gov.in/sih2026PS` (verified 18 Sep 2026).
2. Department of Land Resources, *Bhu-Aadhar : Unique Land Parcel Identification Number (ULPIN)*, `https://dolr.gov.in/en/ulpin/` (updated 25 Apr 2024).
3. Department of Land Resources, DILRMP / ULPIN guidelines PDF, `https://cdnbbsr.s3waas.gov.in/s3d69116f8b0140cdeb1f99a4d5096ffe4/uploads/2024/04/20240425160100930.pdf`.
4. DoLR, DILRMP programme page, `https://dolr.gov.in/en/programmes-schemes/dilrmp-2/`.
5. DST, *National Geospatial Policy 2022*, Gazette S.O. 6095(E), 28 Dec 2022, `https://dst.gov.in/sites/default/files/National%20Geospatial%20Policy.pdf`.
6. Survey of India, CORS, `https://www.surveyofindia.gov.in/pages/continuously-operating-reference-stations-cors-` and `https://cors.surveyofindia.gov.in/`.
7. NRSC, CartoDEM product policy, `https://www.nrsc.gov.in/nrscnew/Dataproducts_Thematic_cartodem.php`; Bhuvan FAQ (CartoDEM ~30 m, ~8 m vertical 90%).
8. ISO 19152-1:2024; ISO 19152-2:2025 Land Administration Domain Model.
9. ISO 8000-118:2025 Natural Location Identifiers (ECCMA lineage).
10. OGC CityGML 3.0 Conceptual Model, OGC 20-010, `https://docs.ogc.org/is/20-010/20-010.html`.
11. PostGIS SFCGAL: `CG_Extrude`, `CG_MakeSolid`, `CG_Volume`, `CG_3DIntersection`, `https://postgis.net/docs/`.
12. The Real Estate (Regulation and Development) Act, 2016, s.17, India Code.
13. Tamil Nadu Apartment Ownership Act, 2022; Karnataka Apartment Ownership Act, 1972; Punjab Apartment Ownership Act, 1995.

### Tier 2 — Academic / FIG

14. FIG, *Best Practices 3D Cadastres*, `https://www.fig.net/resources/publications/figpub/FIG_3DCad/FIG_3DCad-final.pdf`.
15. Kalogianni et al., LADM Edition II design including 3D, *Land Use Policy* / GDMC 2024, `https://www.gdmc.nl/publications/2024/LUP_LADM_Ed2.pdf`.
16. Stoter et al., Dutch 3D registration (Delft 2016), *ISPRS Int. J. Geo-Inf.* 2017, https://doi.org/10.3390/ijgi6060158.
17. Guo / Li / Ying et al., Shenzhen 3D cadastre practice (FIG / *Computers, Environment and Urban Systems* 2013).
18. Andinasari, *Point Cloud for 3D Land Administration System*, MSc TU Delft 2025, `https://www.gdmc.nl/publications/2025/MScThesisCitraAndinasari.pdf`.
19. Vijaywargiya & Ramiya, TALD, *IEEE Access* 2025, https://doi.org/10.1109/ACCESS.2025.3546628.
20. Storey histogram / RANSAC indoor segmentation: *Remote Sensing* 2018, https://doi.org/10.3390/rs10081281; ISPRS Annals 2024 X-4/W5-289.
21. Unsupervised ALS building mapping, arXiv:2205.14585 (not peer-reviewed; method family only).
22. Current Science papers on Indian geodetic / CORS vs NSRF inconsistency (2023–2025), e.g. https://doi.org/10.18520/cs/v127/i2/147-152.

### Tier 3 — Implementations / datasets

23. Queensland Registrar of Titles Directions for the Preparation of Plans (Building vs Volumetric format), 2025.
24. Singapore Land Authority, Survey Maps and Plans (CP / CPST / subterranean RT).
25. CesiumJS documentation (globe translucency, 3D Tiles, vector draping).
26. Open3D `segment_plane`; PDAL CSF filter documentation.
27. 3DCityDB / py3dtilers (export path, not MVP core).

### Tier 4 — Discovery only (not authority)

28. Community SIH mirrors (sih2026.vuce.in, GitHub scrapes of sih.gov.in). Used only to locate PS IDs; official text taken from sih.gov.in.
29. GitHub: citrandina/PointCloud3DLAS, MertcanErdem/LasBuildSeg, TestbedLU/Article-LADM-IFC-CityGML — implementation ideas only.

---

*End of master specification. If a later official DoLR 3D ULPIN schema is published, replace §11 display format but keep UUID persistence and legal-space model.*
