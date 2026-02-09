import json
from typing import List, Dict, Any

def get_all_themes(cursor) -> List[Dict]:
    """Get all themes."""
    cursor.execute("SELECT name, display_name, is_dark FROM themes ORDER BY name")
    return [dict(row) for row in cursor.fetchall()]

def get_theme_by_name(cursor, name: str) -> Dict:
    """Get full theme details including CSS variables."""
    cursor.execute("SELECT * FROM themes WHERE name = ?", (name,))
    row = cursor.fetchone()
    
    if not row:
        return None
        
    result = dict(row)
    result['css_variables'] = json.loads(result['css_variables'])
    return result

def create_theme(cursor, name: str, display_name: str, css_variables: Dict, is_dark: bool = True):
    """Create or update a theme."""
    cursor.execute("""
        INSERT INTO themes (name, display_name, is_dark, css_variables)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(name) DO UPDATE SET
            display_name = excluded.display_name,
            is_dark = excluded.is_dark,
            css_variables = excluded.css_variables
    """, (name, display_name, is_dark, json.dumps(css_variables)))
