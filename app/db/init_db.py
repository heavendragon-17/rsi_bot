import os
import json
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from .models import Base, Theme

def init_database(db_path: str = "data/backtest.db"):
    """Create database and tables if they don't exist."""
    # Ensure data directory exists
    data_dir = os.path.dirname(db_path)
    if data_dir and not os.path.exists(data_dir):
        os.makedirs(data_dir)

    # Create engine
    # Use relative path for SQLite if not absolute
    if not db_path.startswith("sqlite:///"):
        db_url = f"sqlite:///{db_path}"
    else:
        db_url = db_path

    engine = create_engine(db_url)

    # Create tables
    Base.metadata.create_all(engine)

    # Initialize themes
    SessionLocal = sessionmaker(bind=engine)
    with SessionLocal() as session:
        # Check if themes exist
        existing_themes = session.execute(select(Theme)).scalars().first()
        if not existing_themes:
            _insert_default_themes(session)

def _insert_default_themes(session):
    """Insert default themes."""
    themes = [
        {
            "name": "dark",
            "is_active": True,
            "colors_json": json.dumps({
                "bg": "#0f172a",
                "surface": "#1e293b",
                "text": "#f8fafc",
                "primary": "#3b82f6"
            })
        },
        {
            "name": "light",
            "is_active": False,
            "colors_json": json.dumps({
                "bg": "#ffffff",
                "surface": "#f1f5f9",
                "text": "#0f172a",
                "primary": "#2563eb"
            })
        },
        {
            "name": "midnight",
            "is_active": False,
            "colors_json": json.dumps({
                "bg": "#020617",
                "surface": "#0f172a",
                "text": "#e2e8f0",
                "primary": "#6366f1"
            })
        }
    ]

    for t in themes:
        theme = Theme(
            name=t["name"],
            is_active=t["is_active"],
            colors_json=t["colors_json"]
        )
        session.add(theme)

    session.commit()
