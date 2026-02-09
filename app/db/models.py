from sqlalchemy import Column, Integer, String, Float, Text, ForeignKey, LargeBinary, Boolean
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

class Run(Base):
    __tablename__ = 'runs'

    id = Column(Integer, primary_key=True, autoincrement=True)
    strategy_name = Column(String, nullable=False)
    symbol = Column(String, nullable=False)
    timeframe = Column(String, nullable=False)
    start_date = Column(String, nullable=False)  # ISO format
    end_date = Column(String, nullable=False)    # ISO format
    created_at = Column(String, nullable=False)  # ISO timestamp
    config_json = Column(Text)                   # JSON string

    # Relationships
    results = relationship("RunResult", back_populates="run", uselist=False, cascade="all, delete-orphan")
    timeseries = relationship("RunTimeseries", back_populates="run", uselist=False, cascade="all, delete-orphan")
    trades = relationship("Trade", back_populates="run", cascade="all, delete-orphan")

class RunResult(Base):
    __tablename__ = 'run_results'

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(Integer, ForeignKey('runs.id'), nullable=False)
    total_profit = Column(Text, nullable=False)  # Decimal as TEXT
    win_rate = Column(Float)
    total_trades = Column(Integer)
    profit_factor = Column(Float)
    max_drawdown = Column(Text)                  # Decimal as TEXT
    sharpe_ratio = Column(Float)
    metrics_json = Column(Text)                  # Additional metrics JSON

    run = relationship("Run", back_populates="results")

class RunTimeseries(Base):
    __tablename__ = 'run_timeseries'

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(Integer, ForeignKey('runs.id'), nullable=False)
    equity_curve = Column(LargeBinary)      # zlib compressed
    drawdown_curve = Column(LargeBinary)    # zlib compressed

    run = relationship("Run", back_populates="timeseries")

class Trade(Base):
    __tablename__ = 'trades'

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(Integer, ForeignKey('runs.id'), nullable=False)
    entry_time = Column(String, nullable=False)
    exit_time = Column(String)
    entry_price = Column(Text, nullable=False)   # Decimal as TEXT
    exit_price = Column(Text)                    # Decimal as TEXT
    quantity = Column(Text, nullable=False)      # Decimal as TEXT
    side = Column(String, nullable=False)        # 'long' or 'short'
    pnl = Column(Text)                           # Decimal as TEXT
    exit_reason = Column(String)                 # 'tp', 'sl', 'signal', 'timeout'

    run = relationship("Run", back_populates="trades")

class Theme(Base):
    __tablename__ = 'themes'

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, unique=True, nullable=False)
    is_active = Column(Boolean, default=False)   # SQLite INTEGER 0/1
    colors_json = Column(Text, nullable=False)   # JSON string
