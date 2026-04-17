"""
Preset CRUD routes — save/load/delete backtest configuration presets.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.schemas import PresetCreate, PresetResponse, PresetUpdate
from app.repository.backtest.database import SessionLocal
from app.repository.backtest.models import Preset

router = APIRouter(prefix="/api/presets", tags=["presets"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("", response_model=list[PresetResponse])
def list_presets(strategy: str | None = None, db: Session = Depends(get_db)):
    query = db.query(Preset)
    if strategy:
        query = query.filter(Preset.strategy == strategy)
    rows = query.order_by(Preset.updated_at.desc()).all()
    return [
        PresetResponse(
            id=r.id,
            name=r.name,
            strategy=r.strategy,
            config=r.config,
            created_at=r.created_at.isoformat() if r.created_at else "",
            updated_at=r.updated_at.isoformat() if r.updated_at else "",
        )
        for r in rows
    ]


@router.post("", status_code=201, response_model=PresetResponse)
def create_preset(body: PresetCreate, db: Session = Depends(get_db)):
    preset = Preset(name=body.name, strategy=body.strategy, config=body.config)
    db.add(preset)
    db.commit()
    db.refresh(preset)
    return PresetResponse(
        id=preset.id,
        name=preset.name,
        strategy=preset.strategy,
        config=preset.config,
        created_at=preset.created_at.isoformat() if preset.created_at else "",
        updated_at=preset.updated_at.isoformat() if preset.updated_at else "",
    )


@router.put("/{preset_id}", response_model=PresetResponse)
def update_preset(preset_id: int, body: PresetUpdate, db: Session = Depends(get_db)):
    preset = db.query(Preset).filter_by(id=preset_id).first()
    if not preset:
        raise HTTPException(404, "Preset not found")
    if body.name is not None:
        preset.name = body.name
    if body.config is not None:
        preset.config = body.config
    db.commit()
    db.refresh(preset)
    return PresetResponse(
        id=preset.id,
        name=preset.name,
        strategy=preset.strategy,
        config=preset.config,
        created_at=preset.created_at.isoformat() if preset.created_at else "",
        updated_at=preset.updated_at.isoformat() if preset.updated_at else "",
    )


@router.delete("/{preset_id}", status_code=204)
def delete_preset(preset_id: int, db: Session = Depends(get_db)):
    preset = db.query(Preset).filter_by(id=preset_id).first()
    if not preset:
        raise HTTPException(404, "Preset not found")
    db.delete(preset)
    db.commit()
