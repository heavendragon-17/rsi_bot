import json
from typing import List, Dict, Any, Optional

def get_all_strategies(cursor) -> List[Dict]:
    """Get all available strategies."""
    cursor.execute("SELECT id, name, description FROM strategies ORDER BY name")
    return [dict(row) for row in cursor.fetchall()]

def get_strategy_by_name(cursor, name: str) -> Optional[Dict]:
    """Get strategy details and default config."""
    cursor.execute("SELECT * FROM strategies WHERE name = ?", (name,))
    row = cursor.fetchone()
    if not row:
        return None
    
    result = dict(row)
    result['default_config'] = json.loads(result['default_config'])
    return result

def create_strategy(cursor, name: str, default_config: Dict, description: str = None):
    """Create or update a strategy."""
    cursor.execute("""
        INSERT INTO strategies (name, description, default_config)
        VALUES (?, ?, ?)
        ON CONFLICT(name) DO UPDATE SET
            description = excluded.description,
            default_config = excluded.default_config
    """, (name, description, json.dumps(default_config)))
