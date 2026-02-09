import pandas as pd
import os

def load_csv_data(filepath: str) -> pd.DataFrame:
    """Load CSV data into DataFrame."""
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"Data file not found: {filepath}")

    # Minimal implementation for now
    df = pd.read_csv(filepath)
    # Ensure standard columns if needed
    return df
