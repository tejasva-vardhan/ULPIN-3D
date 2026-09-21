import React, { Suspense, useEffect, useMemo } from 'react'
import { Canvas, useThree } from '@react-three/fiber'
import { OrbitControls, Grid, Line, Environment, AdaptiveDpr } from '@react-three/drei'
import * as THREE from 'three'
import Prism from './Prism.jsx'
import { makeProjector, findOrigin, ringToPoints } from './viewerGeo.js'

const SOLID_CLASSES = new Set(['FLOOR', 'UNIT', 'COMMON', 'PARKING', 'BALCONY', 'AIR', 'SUBSURFACE', 'UTILITY'])

function frameForUnits(units) {
  const project = makeProjector(findOrigin(units))
  const bounds = { minX: Infinity, minY: Infinity, minZ: Infinity,
    maxX: -Infinity, maxY: -Infinity, maxZ: -Infinity }
  for (const unit of units) {
    for (const ring of unit.geojson?.coordinates || []) {
      for (const point of ring) {
        const [x, z] = project(point)
        bounds.minX = Math.min(bounds.minX, x)
        bounds.maxX = Math.max(bounds.maxX, x)
        bounds.minZ = Math.min(bounds.minZ, z)
        bounds.maxZ = Math.max(bounds.maxZ, z)
      }
    }
    bounds.minY = Math.min(bounds.minY, unit.zmin)
    bounds.maxY = Math.max(bounds.maxY, unit.zmax)
  }
  if (!Number.isFinite(bounds.minX)) {
    return { target: [0, 0, 0], position: [45, 35, 45], span: 30 }
  }
  const target = [
    (bounds.minX + bounds.maxX) / 2,
    (bounds.minY + bounds.maxY) / 2,
    (bounds.minZ + bounds.maxZ) / 2,
  ]
  const span = Math.max(bounds.maxX - bounds.minX, bounds.maxY - bounds.minY,
    bounds.maxZ - bounds.minZ, 20)
  return {
    target,
    position: [target[0] + span * 1.35, target[1] + span * 1.05, target[2] + span * 1.35],
    span,
  }
}

function CameraFrame({ frame, controlsRef }) {
  const camera = useThree((state) => state.camera)
  useEffect(() => {
    camera.position.set(...frame.position)
    camera.far = Math.max(500, frame.span * 20)
    camera.lookAt(...frame.target)
    camera.updateProjectionMatrix()
    if (controlsRef.current) {
      controlsRef.current.target.set(...frame.target)
      controlsRef.current.update()
      controlsRef.current.saveState()
    }
  }, [camera, controlsRef, frame])
  return null
}

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
  const frame = useMemo(() => frameForUnits(units), [units])
  return (
    <Canvas shadows dpr={[1, 1.75]} camera={{ position: frame.position, fov: 42, near: 0.1, far: Math.max(500, frame.span * 20) }} onPointerMissed={onPointerMissed}>
      <color attach="background" args={['#eceeec']} />
      <fog attach="fog" args={['#eceeec', 60, 160]} />
      <Suspense fallback={null}>
        <Scene units={units} selectedId={selectedId} onSelect={onSelect} onHover={onHover} explode={explode} hiddenClasses={hiddenClasses} />
        <Environment preset="city" environmentIntensity={0.25} />
      </Suspense>
      <CameraFrame frame={frame} controlsRef={controlsRef} />
      <OrbitControls
        ref={controlsRef}
        target={frame.target}
        makeDefault
        autoRotate={autoRotate}
        autoRotateSpeed={0.7}
        enableDamping
        dampingFactor={0.08}
        minDistance={8}
        maxDistance={Math.max(140, frame.span * 5)}
        maxPolarAngle={Math.PI / 2.04}
      />
      <AdaptiveDpr />
    </Canvas>
  )
}
