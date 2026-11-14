from sqlalchemy import String, Integer, Double, ForeignKey, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column
from src.config.database import Base
class Stall(Base):
    __tablename__ = 'stalls'
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    current_job_id: Mapped[int | None] = mapped_column(ForeignKey('jobs.id'), nullable=True)
class CapacityDay(Base):
    __tablename__ = 'capacity_days'
    date: Mapped[str] = mapped_column(String(10), primary_key=True)
    capacity: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[float] = mapped_column(Double, default=0)
    updated_by: Mapped[str] = mapped_column(String(120), default='')
class Occupancy(Base):
    __tablename__ = 'occupancies'
    __table_args__ = (UniqueConstraint('job_id', 'date'), Index('ix_occupancies_date', 'date'), Index('ix_occupancies_stall', 'stall'))
    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey('jobs.id'))
    stall: Mapped[str] = mapped_column(String(120), default='')
    date: Mapped[str] = mapped_column(String(10))
    portions: Mapped[int] = mapped_column(Integer, default=0)
