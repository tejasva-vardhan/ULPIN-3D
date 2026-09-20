import React from 'react'
import { motion } from 'framer-motion'
import { FileBox, FileCode2, FileJson2, Download } from 'lucide-react'
import { Card, Button } from '../components/ui/primitives.jsx'
import { modelGltfUrl, exportCityGmlUrl, exportGeoJsonUrl } from '../lib/api.js'

const EXPORTS = [
  {
    key: 'gltf',
    title: 'glTF prisms',
    icon: FileBox,
    tone: 'text-accent-blue',
    description: 'Minimal glTF 2.0 of unit prisms in local metres — for viewers and CAD tools, not a legal document.',
    url: () => modelGltfUrl(),
    filename: 'ulpin3d-model.gltf',
  },
  {
    key: 'citygml',
    title: 'CityGML LOD1',
    icon: FileCode2,
    tone: 'text-accent-violet',
    description: 'Physical building envelope only, CityGML 2.0 LOD1. Legal 3D spaces stay in PostGIS; this is a spatial export, not title.',
    url: (siteId) => exportCityGmlUrl(siteId),
    filename: 'ulpin3d-building-lod1.gml',
  },
  {
    key: 'geojson',
    title: 'Validated GeoJSON',
    icon: FileJson2,
    tone: 'text-accent-aqua',
    description: 'Every VALID, active spatial unit footprint with its metadata, in EPSG:4326 — flat footprints, not volumes.',
    url: (siteId) => exportGeoJsonUrl(siteId),
    filename: 'ulpin3d-validated.geojson',
  },
]

export default function ExportPage({ siteId }) {
  return (
    <div className="space-y-6">
      <p className="max-w-2xl text-xs leading-relaxed text-ink-secondary">
        Every export below carries the same disclaimer as the rest of this prototype: nothing here is an official DoLR
        identifier or legal title. Exports reflect the current ACTIVE, VALID state of the selected scope.
      </p>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {EXPORTS.map((exp, i) => (
          <motion.div key={exp.key} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.06 }}>
            <Card className="flex h-full flex-col p-5">
              <exp.icon size={20} className={exp.tone} />
              <h3 className="mt-3 text-sm font-semibold text-ink-primary">{exp.title}</h3>
              <p className="mt-1.5 flex-1 text-xs leading-relaxed text-ink-secondary">{exp.description}</p>
              <a href={exp.url(siteId)} download={exp.filename} className="mt-4">
                <Button variant="ghost" icon={Download} className="w-full">
                  Download
                </Button>
              </a>
            </Card>
          </motion.div>
        ))}
      </div>
    </div>
  )
}
