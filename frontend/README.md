# Stratum frontend

A React + Tailwind + Framer Motion rewrite of the Stratum workspace, centered on a
live, interactive 3D viewer built with `three.js` / `@react-three/fiber`.

## Run it

This is a plain Vite dev-server app, independent of the backend's docker-compose —
point it at wherever the FastAPI API is running.

```bash
cd frontend
npm install
cp .env.example .env     # edit VITE_API_BASE if the API isn't on localhost:8000
npm run dev              # http://localhost:5173
```

Start the backend separately (`docker-compose up` in the repo root, or `uvicorn
app.main:app --reload`) — CORS is already wide open (`allow_origins=["*"]` in
`app/main.py`), so the two just need to both be running.

`npm run build` produces a static `dist/` you can serve however you like
(nginx, `vite preview`, a CDN) if you want a built artifact instead of the dev
server for the actual demo.

## What's here

- **Overview** — health, KPIs, topology-health meters, a quick "seed the demo" flow.
- **Sites** / **Import & Process** — register a site, import property GeoJSON, upload
  LAS/DSM/DTM evidence, and run the classical elevation → building pipeline.
- **Spatial Units** — filterable table of every unit, opens a full record card.
- **3D Model** — the centerpiece: live, interactive prisms extruded client-side from
  each unit's validated footprint + height, colored by class and by topology status,
  with an "explode" slider, hover/click inspection, and a side panel wired straight
  into issuance and review.
- **Validation** — rule-by-rule pass/fail bars and the raw findings table.
- **Rights & Parties** — create parties/administrative units, record RIGHT /
  RESTRICTION / RESPONSIBILITY entries.
- **Review Queue** — approve/reject DEGRADED units, release review blocks with
  evidence, see review history.
- **Export** — glTF, CityGML LOD1, and validated GeoJSON downloads.

## Notes on the 3D viewer

It does **not** load the baked `/model.gltf` export. Instead it fetches
`GET /spatial-units`, projects each unit's WGS84 footprint into local metres
around a shared origin (a small-scale equirectangular approximation — fine at
site scale), and extrudes it client-side with `THREE.ExtrudeGeometry`. That's
what makes per-unit click/hover, color-by-status, and the explode view possible;
the glTF/CityGML endpoints stay available as static exports on the Export page.

## Verified demo path

The frontend builds with Vite and has been checked in a browser against the
isolated Docker demo. The API's `/events` stream drives the live activity feed.
For a repeatable presentation scene, use the root [demo runbook](../DEMO.md).
