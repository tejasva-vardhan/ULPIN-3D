import React, { useMemo, useRef, useState } from 'react'
import { useFrame } from '@react-three/fiber'
import * as THREE from 'three'
import { extrudeUnit } from './viewerGeo.js'
import { classMeta, statusMeta } from '../../lib/format.js'

// One extruded legal volume. Handles its own hover/select highlight, a
// DEGRADED pulse, and a smooth "explode" lift so floors can be peeled apart
// to see inside the building.
export default function Prism({ unit, project, selected, onSelect, onHover, explode, dimmed }) {
  const geometry = useMemo(() => extrudeUnit(unit, project), [unit, project])
  const meshRef = useRef()
  const [hovered, setHovered] = useState(false)

  const cls = classMeta(unit.su_class)
  const status = statusMeta(unit.topology_status)
  const targetLift = explode * Math.max(unit.zmin, 0) * 0.55

  useFrame((state) => {
    if (!meshRef.current) return
    meshRef.current.position.y = THREE.MathUtils.lerp(meshRef.current.position.y, targetLift, 0.12)

    const mat = meshRef.current.material
    if (unit.topology_status === 'DEGRADED') {
      const pulse = 0.55 + Math.sin(state.clock.elapsedTime * 2.6) * 0.25
      mat.emissiveIntensity = pulse
    } else if (selected || hovered) {
      mat.emissiveIntensity = THREE.MathUtils.lerp(mat.emissiveIntensity, 0.85, 0.2)
    } else {
      mat.emissiveIntensity = THREE.MathUtils.lerp(mat.emissiveIntensity, 0.12, 0.2)
    }
  })

  if (!geometry) return null

  const baseColor = unit.topology_status === 'INVALID' ? '#e34948' : cls.color
  const opacity = dimmed ? 0.08 : unit.topology_status === 'PENDING' ? 0.55 : unit.su_class === 'UTILITY' ? 0.7 : 0.92

  return (
    <mesh
      ref={meshRef}
      geometry={geometry}
      castShadow
      receiveShadow
      onClick={(e) => {
        e.stopPropagation()
        onSelect(unit)
      }}
      onPointerOver={(e) => {
        e.stopPropagation()
        setHovered(true)
        onHover(unit, e)
        document.body.style.cursor = 'pointer'
      }}
      onPointerOut={() => {
        setHovered(false)
        onHover(null)
        document.body.style.cursor = 'auto'
      }}
      onPointerMove={(e) => hovered && onHover(unit, e)}
    >
      <meshStandardMaterial
        color={baseColor}
        emissive={status.color}
        emissiveIntensity={0.12}
        transparent
        opacity={opacity}
        roughness={0.45}
        metalness={0.12}
        side={THREE.DoubleSide}
      />
      {(selected || hovered) && (
        <lineSegments>
          <edgesGeometry args={[geometry]} />
          <lineBasicMaterial color={selected ? '#0b0b0b' : baseColor} linewidth={1.5} />
        </lineSegments>
      )}
    </mesh>
  )
}
