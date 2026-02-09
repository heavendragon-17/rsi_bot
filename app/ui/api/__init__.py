from app.ui.api.backtest import BacktestAPI
import os

class BridgeAPI(BacktestAPI):
    """
    Main API bridge exposed to PyWebView.
    Inherits from functional APIs.
    """
    def __init__(self):
        super().__init__()
        print("BridgeAPI initialized")

    def version(self):
        return "1.0.0"
        
    def echo(self, message):
        return f"Echo: {message}"

    def read_file(self, filename: str):
        """Read a file from the project root (safe-guarded)."""
        try:
            # Basic security: only allow specific files
            allowed_files = ['config.yaml']
            if filename not in allowed_files:
                return {"success": False, "error": "File access denied"}
            
            # Determine path (assuming run from project root or relative)
            # Safe way: use a PROJECT_ROOT constant or similar if available, or relative to cwd
            if os.path.exists(filename):
                with open(filename, 'r', encoding='utf-8') as f:
                    content = f.read()
                return {"success": True, "data": content}
            else:
                return {"success": False, "error": "File not found"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def save_file(self, filename: str, content: str):
        """Save a file to the project root (safe-guarded)."""
        try:
            allowed_files = ['config.yaml']
            if filename not in allowed_files:
                 return {"success": False, "error": "File access denied"}
            
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(content)
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}
