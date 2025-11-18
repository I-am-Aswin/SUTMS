from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    DateTime,
    ForeignKey,
    func,
    Index,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class Collection(Base):
    __tablename__ = "collections"
    id = Column(String(100), primary_key=True)
    title = Column(String(255), nullable=False)
    description = Column(Text)
    created_at = Column(DateTime, server_default=func.now())

    objects = relationship("STIXObject", back_populates="collection")


class STIXObject(Base):
    __tablename__ = "stix_objects"
    id = Column(Integer, primary_key=True, autoincrement=True)
    object_id = Column(String(255), nullable=False, index=True)
    object_type = Column(String(100), nullable=False, index=True)
    raw = Column(Text, nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    collection_id = Column(String(100), ForeignKey("collections.id"), nullable=False)

    collection = relationship("Collection", back_populates="objects")


# indexes
Index("ix_stix_objects_object_id", STIXObject.object_id)
Index("ix_stix_objects_object_type", STIXObject.object_type)
