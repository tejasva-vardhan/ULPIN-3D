# Internal demo

Start the isolated demo from the repository root:

```powershell
docker compose -f docker-compose.demo.yml up -d --build
```

Open [the scripted demo](http://localhost:8001/demo). Confirm that [the health check](http://localhost:8001/health) reports `ok: true`, `sfcgal: true`, and `spatial_units: 24`.

## Four-minute walkthrough

1. Click **Parcel + parent**, then **Play demo**. Explain that the surface ULPIN names the land and the proposed extension names volumes above and below it.
2. Show Flat 501, the common corridor, and the underground water corridor. Explain that one surface parcel can contain several vertically distinct spaces and rights.
3. Click **Run validation**. The seeded duplicate is deliberately invalid. Click **Fix overlap** to repair it and issue Flat 501's proposed identifier.
4. Open **Record card**, then show the CityGML or Legal GeoJSON export. Explain that the record retains provenance and rights information.

On **Import → Elevation → building**, the floor workflow exposes its evidence clearly: a selected plan supplies explicit floor and apartment boundaries; declared storeys create equal-height proposals; height-only input creates inferred bands. Generated bands stay blocked for review and never claim that airborne LiDAR observed internal slabs.

On **Import → Underground utility**, load the synthetic example, select the demo site, and create the corridor. The form turns the centre-line, diameter, depth, and declared ground elevation into a review-required 3D volume, then shows its vertical range, volume, and clash findings. The same example is available at `data/examples/utility_centreline.geojson`.

If a rehearsal changes the scene, click **Restore plans** before presenting. The demo uses its own database and does not modify the normal development database.

## Claims to use

- The identifiers are proposed 3D ULPIN extensions under a labelled placeholder parent. They are not government-issued identifiers or ownership certificates.
- The presentation scene is synthetic and demonstrates the complete workflow.
- The separate [three-building public-data check](data/public/nyc_2017_945172/README.md) has a median footprint IoU of 0.593 and median absolute height error of 0.20 m. It is a small selected sample, not a cadastral accuracy certification.

Stop the isolated stack with:

```powershell
docker compose -f docker-compose.demo.yml down
```

## DSCE Building No. 05 field case

This case uses the real OpenStreetMap footprint for way `347171800` and the
three storeys observed during the team field visit on 2026-09-21. Its parcel is
only a demonstration analysis envelope. Its 3 m floor heights are declared
assumptions awaiting survey or LiDAR measurement, so all five imported spatial
units deliberately enter the review queue.

Start the React interface against the isolated demo API in a second PowerShell
window:

```powershell
cd frontend
$env:VITE_API_BASE="http://localhost:8001"
npm run dev
```

Then open [the React interface](http://localhost:5173) and use these values:

1. On **Sites**, create a site named `DSCE Mechanical Engineering Block 05`.
   Enter `DSCE05DEMO0001` as the labelled 14-character placeholder parent
   ULPIN, `4326` as the source EPSG, and `LOCAL_SITE` as the height reference.
   Click **Use this site** after creation.
2. On **Import & Process → Property GeoJSON**, select
   `data/examples/dsce_mechanical_block_05.geojson`. Choose the DSCE site, keep
   dataset kind as `floor_plans`, set source EPSG to `4326`, and select
   `MANUAL` as the default geometry origin.
3. Click **Import dataset**. In the imported datasets list, find that filename
   and click **Process**. The expected result is five spatial units and five
   extruded solids.
4. Keep the DSCE site selected and open **3D Model**. The layer list must include
   **Floor**. Use the explode slider to separate and select the Ground, First,
   and Second Floor volumes at 0–3 m, 3–6 m, and 6–9 m.
5. On **Spatial Units** or **Review Queue**, confirm that the analysis envelope,
   building, and floors are marked for review. This is expected: the workflow
   preserves the OSM footprint but does not promote assumed heights or a
   non-cadastral envelope to surveyed facts.

Do not describe these floor bands as LiDAR-derived, surveyed, or ownership
boundaries. No rooms, owners, rights, or official identifiers are included in
this case.

### Two-building campus view

To demonstrate simultaneous vertical mapping, create a fresh site named
`DSCE Two-Building Campus Demo` with placeholder parent `DSCETWODEMO001`, then
repeat the property import using `data/examples/dsce_two_building_demo.geojson`.
The expected result is nine spatial units and nine extruded solids: one analysis
envelope, Buildings 05 and 07, and three floor volumes under each building.
Both footprints preserve their respective OSM geometries. All vertical bands
remain review-required assumptions.
