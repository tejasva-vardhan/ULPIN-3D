# Three-building public-data check

This reproducible check runs the current building extraction and height estimator on three real buildings in Staten Island, New York. It is separate from the synthetic Indian 3D ULPIN demo. It does not assess apartment boundaries, underground rights, legal ownership, or city-scale performance.

## Inputs and provenance

| Input | Source | Local file |
| --- | --- | --- |
| 2017 airborne LiDAR tile `945172.las` | [New York State tile index](https://orthos.its.ny.gov/arcgis/rest/services/vector/las_indexes/MapServer/10); [direct tile](https://gisdata.ny.gov/elevation/LIDAR/NYC_TopoBathymetric2017/945172.las) | Downloaded only when recreating crops; ignored by Git |
| Buildings `DOITT_ID 684044`, `836939`, and `150985` | [NYC Building Footprints API](https://data.cityofnewyork.us/resource/5zhs-2jue.json); [metadata](https://github.com/CityOfNewYork/nyc-geo-metadata/blob/main/Metadata/Metadata_BuildingFootprints.md) | `nyc_building_*.json` |
| Matching tax lots `5010700001`, `5010700020`, and `5010680096` | [NYC Tax Lot Polygon API](https://data.cityofnewyork.us/resource/i38t-6if2.json) | `nyc_tax_lot_*.json` |

The LiDAR was collected in 2017. Each building record says `Photogrammetric`; its public record does not identify the exact source used for that building's roof height. The tax-lot endpoints are current public records, so their geometry is not guaranteed to be identical to the 2017 lots. Source records were retrieved on 20 September 2026. The full LiDAR tile SHA-256 is `2d0870ec64fd0fcd06bc0c6b9b516b47ee5c5602178b08844bacbecf24052a77`.

The source LAS uses NAD83 New York Long Island / NAVD88 in US survey feet. The preparation script crops it to each lot plus 6 metres and converts horizontal coordinates to EPSG:32618 and elevation values to metres. Each selected lot has one mapped building and fully covers its reference outline.

## Results

| Building | Footprint IoU | Estimated height | City height | Absolute height error |
| --- | ---: | ---: | ---: | ---: |
| 684044 | 0.856 | 11.18 m | 10.47 m | 0.71 m |
| 836939 | 0.593 | 7.39 m | 7.26 m | 0.13 m |
| 150985 | 0.418 | 8.18 m | 7.98 m | 0.20 m |
| **Median** | **0.593** | — | — | **0.20 m** |

The files do not classify building points, so the estimator fits a local ground plane and screens elevated unclassified returns for locally smooth surfaces. It refuses parcels containing more than one substantial candidate unless a plan footprint or smaller parcel is supplied. The footprint metric compares against photogrammetric outlines, while the individual city height measurement methods are unspecified. Three deliberately selected buildings are not a representative accuracy benchmark. The complete machine-readable result is in `report.json`; its `confidence` is a heuristic, not a probability.

## Reproduce

From the repository root:

```powershell
docker compose -f docker-compose.demo.yml build api
docker run --rm -v "${PWD}/backend:/code" -v "${PWD}/data/public/nyc_2017_945172:/sample" ulpin-3d-demo-api python scripts/prepare_nyc_sample.py --data-dir /sample --download
docker run --rm -v "${PWD}/backend:/code" -v "${PWD}/data/public/nyc_2017_945172:/sample" ulpin-3d-demo-api python scripts/prepare_nyc_sample.py --data-dir /sample --building-id 836939
docker run --rm -v "${PWD}/backend:/code" -v "${PWD}/data/public/nyc_2017_945172:/sample" ulpin-3d-demo-api python scripts/prepare_nyc_sample.py --data-dir /sample --building-id 150985
docker run --rm -v "${PWD}/backend:/code" -v "${PWD}/data/public/nyc_2017_945172:/sample" ulpin-3d-demo-api python -m app.evaluation /sample/case.json /sample/case_836939.json /sample/case_150985.json --output /sample/report.json
```

The `.las` files are ignored by Git. The raw tile is about 126 MB and can be deleted after preparing the crops. The retained crops total about 9.7 MB, allowing the evaluator to run again without a download.
