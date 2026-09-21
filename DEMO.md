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
