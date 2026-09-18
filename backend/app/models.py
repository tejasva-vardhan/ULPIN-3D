from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import DeclarativeBase
from geoalchemy2 import Geometry


class Base(DeclarativeBase):
    pass


class SpatialUnit(Base):
    __tablename__ = "spatial_unit"
    __table_args__ = (
        CheckConstraint("zmax > zmin"),
        UniqueConstraint("parent_ulpin", "su_class", "local_code", "version"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True)
    parent_id = Column(UUID(as_uuid=True), ForeignKey("spatial_unit.id"))
    parent_ulpin = Column(Text)
    su_class = Column(Enum(name="su_class"), nullable=False)
    local_code = Column(Text, nullable=False)
    version = Column(Integer, nullable=False, default=1)
    display_id = Column(Text, nullable=False, unique=True)
    status = Column(Enum(name="object_status"), nullable=False, default="ACTIVE")
    geom_2d = Column(Geometry("POLYGON", srid=32643), nullable=False)
    zmin = Column(Float, nullable=False)
    zmax = Column(Float, nullable=False)
    geom_3d = Column(Geometry("POLYHEDRALSURFACEZ", srid=32643))
    volume_m3 = Column(Float)
    geom_origin = Column(Enum(name="geom_origin"), nullable=False)
    confidence = Column(Numeric)
    topology_status = Column(Enum(name="topology_status"), nullable=False, default="PENDING")
    geom_hash = Column(Text)
    baunit_id = Column(UUID(as_uuid=True), ForeignKey("baunit.id"))
    valid_from = Column(DateTime(timezone=True), server_default=func.now())
    valid_to = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Building(Base):
    __tablename__ = "building"
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    spatial_unit_id = Column(UUID(as_uuid=True), ForeignKey("spatial_unit.id"), unique=True)
    storeys_above = Column(Integer)
    storeys_below = Column(Integer)
    z_ground = Column(Float)
    z_roof = Column(Float)
    extraction_method = Column(Text)


class Floor(Base):
    __tablename__ = "floor"
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    building_id = Column(UUID(as_uuid=True), ForeignKey("building.id"))
    spatial_unit_id = Column(UUID(as_uuid=True), ForeignKey("spatial_unit.id"), unique=True)
    level_index = Column(Integer, nullable=False)
    label = Column(Text)


class Party(Base):
    __tablename__ = "party"
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    party_type = Column(String, nullable=False)
    name = Column(String, nullable=False)
    ext_ref = Column(Text)


class BaUnit(Base):
    __tablename__ = "baunit"
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    name = Column(Text)
    uid = Column(Text, unique=True)


class RRR(Base):
    __tablename__ = "rrr"
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    baunit_id = Column(UUID(as_uuid=True), ForeignKey("baunit.id"), nullable=False)
    party_id = Column(UUID(as_uuid=True), ForeignKey("party.id"), nullable=False)
    spatial_unit_id = Column(UUID(as_uuid=True), ForeignKey("spatial_unit.id"))
    rrr_type = Column(Enum(name="rrr_type"), nullable=False)
    share = Column(Numeric)
    description = Column(Text)


class SourceDataset(Base):
    __tablename__ = "source_dataset"
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    kind = Column(Text, nullable=False)
    filename = Column(Text, nullable=False)
    checksum_sha256 = Column(Text, nullable=False)
    epsg = Column(Integer)
    z_ref = Column(Text)
    meta = Column(JSONB, default=dict)


class ValidationResult(Base):
    __tablename__ = "validation_result"
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    spatial_unit_id = Column(UUID(as_uuid=True), ForeignKey("spatial_unit.id"))
    run_id = Column(UUID(as_uuid=True), nullable=False)
    rule_code = Column(Text, nullable=False)
    passed = Column(Boolean, nullable=False)
    severity = Column(Text, nullable=False)
    detail = Column(JSONB)


class ProcessRun(Base):
    __tablename__ = "process_run"
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    stage = Column(Text, nullable=False)
    processor_ver = Column(Text, nullable=False)
    source_ids = Column(ARRAY(UUID(as_uuid=True)))
    metrics = Column(JSONB)


class Site(Base):
    __tablename__ = "site"
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    name = Column(Text, nullable=False)
    storage_epsg = Column(Integer, nullable=False, default=32643)
    source_epsg = Column(Integer, nullable=False)
    z_ref = Column(Text, nullable=False)
    parent_ulpin = Column(Text, nullable=False)
    bbox = Column(Geometry("POLYGON", srid=32643))
    meta = Column(JSONB, default=dict)
