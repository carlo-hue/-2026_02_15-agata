#models.py
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import String, DateTime, Text, Integer, Float, ForeignKey
from datetime import datetime
#commnento da carlo
#modificato da giorgio
#secondo modifica
#terza modifica giorgio
#quarta modifica giorgio

class Base(DeclarativeBase):
    pass

class UserState(Base):
    __tablename__ = "user_states"

    state_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

# --- Fase 2 (placeholder): curve reali in DB ---
class Lightcurve(Base):
    __tablename__ = "lightcurves"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

class LightcurvePoint(Base):
    __tablename__ = "lightcurve_points"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    lightcurve_id: Mapped[int] = mapped_column(Integer, ForeignKey("lightcurves.id"), index=True, nullable=False)
    session_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    jd: Mapped[float] = mapped_column(Float, index=True, nullable=False)
    mag: Mapped[float] = mapped_column(Float, nullable=False)
    point_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)