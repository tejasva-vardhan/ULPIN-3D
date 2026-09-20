import React, { Suspense, useMemo } from 'react'
import { Canvas } from '@react-three/fiber'
import { OrbitControls, Grid, Line, Environment, AdaptiveDpr } from '@react-three/drei'
import * as THREE from 'three'
import Prism from './Prism.jsx'
import { makeProjector, findOrigin, ringToPoints } from './viewerGeo.js'

const SOLID_CLASSES = new Set(['UNIT', 'COMMON', 'PARKING', 'BALCONY', 'AIR', 'SUBSURFACE', 'UTILITY', 'TRANSPORT'])

function ParcelOutline({ unit, project }) {
  const ring = unit.geojson?.coordinates?.[0]
  const points = useMemo(() => (ring ? ringToPoints(ring, project, 0.02) : []), [ring, project])
  if (!points.length) return null
  return <Line points={points} color="#2a78d6" lineWidth={1.4} dashed dashSize={0.6} gapSize={0.4} transparent opacity={0.7} />
}

function BuildingShell({ unit, project }) {
  const ring = unit.geojson?.coordinates?.[0]
  const bottom = useMemo(() => (ring ? ringToPoints(ring, project, unit.zmin) : []), [ring, project, unit.zmin])
  const top = useMemo(() => (ring ? ringToPoints(ring, project, unit.zmax) : []), [ring, project, unit.zmax])
  if (!bottom.length) return null
  return (
    <group>
      <Line points={bottom} color="#898781" lineWidth={1} transparent opacity={0.55} />
      <Line points={top} color="#898781" lineWidth={1} transparent opacity={0.55} />
      {bottom.map((p, i) => (
        <Line key={i} points={[p, top[i]]} color="#898781" lineWidth={1} transparent opacity={0.35} />
      ))}
    </group>
  )
}

function Scene({ units, selectedId, onSelect, onHover, explode, hiddenClasses }) {
  const origin = useMemo(() => findOrigin(units), [units])
  const project = useMemo(() => makeProjector(origin), [origin])

  const parcel = units.find((u) => u.su_class === 'PARCEL')
  const buildings = units.filter((u) => u.su_class === 'BUILDING')
  const solids = units.filter((u) => SOLID_CLASSES.has(u.su_class))

  return (
    <group>
      <ambientLight intensity={0.75} />
      <directionalLight position={[26, 42, 18]} intensity={1.1} castShadow shadow-mapSize={[2048, 2048]} shadow-bias={-0.0005}>
        <orthographicCamera attach="shadow-camera" args={[-40, 40, 40, -40, 1, 120]} />
      </directionalLight>
      <directionalLight position={[-20, 18, -24]} intensity={0.25} color="#2a78d6" />
      <hemisphereLight args={['#ffffff', '#d7d8d2', 0.55]} />

      {parcel && !hiddenClasses.has('PARCEL') && <ParcelOutline unit={parcel} project={project} />}
      {buildings
        .filter((b) => !hiddenClasses.has('BUILDING'))
        .map((b) => (
          <BuildingShell key={b.uuid} unit={b} project={project} />
        ))}
      {solids
        .filter((u) => !hiddenClasses.has(u.su_class))
        .map((u) => (
          <Prism
            key={u.uuid}
            unit={u}
            project={project}
            selected={selectedId === u.uuid}
            onSelect={onSelect}
            onHover={onHover}
            explode={explode}
            dimmed={Boolean(selectedId) && selectedId !== u.uuid}
          />
        ))}

      <Grid
        position={[0, -0.02, 0]}
        args={[10, 10]}
        cellSize={2}
        cellThickness={0.5}
        cellColor="#c3c2b7"
        sectionSize={10}
        sectionThickness={1}
        sectionColor="#2a78d6"
        fadeDistance={90}
        fadeStrength={1.5}
        infiniteGrid
      />
    </group>
  )
}

export default function ModelViewer({ units, selectedId, onSelect, onHover, explode, autoRotate, hiddenClasses, controlsRef, onPointerMissed }) {
  return (
    <Canvas shadows dpr={[1, 1.75]} camera={{ position: [34, 30, 34], fov: 42, near: 0.1, far: 500 }} onPointerMissed={onPointerMissed}>
      <color attach="background" args={['#eceeec']} />
      <fog attach="fog" args={['#eceeec', 60, 160]} />
      <Suspense fallback={null}>
        <Scene units={units} selectedId={selectedId} onSelect={onSelect} onHover={onHover} explode={explode} hiddenClasses={hiddenClasses} />
        <Environment preset="city" environmentIntensity={0.25} />
      </Suspense>
      <OrbitControls
        ref={controlsRef}
        makeDefault
        autoRotate={autoRotate}
        autoRotateSpeed={0.7}
        enableDamping
        dampingFactor={0.08}
        minDistance={8}
        maxDistance={140}
        maxPolarAngle={Math.PI / 2.04}
      />
      <AdaptiveDpr />
    </Canvas>
  )
}
