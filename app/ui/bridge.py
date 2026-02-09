import webview
import sys
import os
from app.ui.api import BridgeAPI

class BacktestUI:
    def __init__(self, debug=False):
        self.debug = debug
        self.api = BridgeAPI()

    def start(self):
        """Start the UI window."""
        # Determine path to UI assets
        if getattr(sys, 'frozen', False):
            # Running as PyInstaller bundle
            base_dir = sys._MEIPASS
        else:
            # Running as script
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

        ui_dir = os.path.join(base_dir, 'ui', 'dist')

        if not os.path.exists(ui_dir):
            # Fallback HTML if UI not built
            html_content = """
            <!DOCTYPE html>
            <html>
            <body style="font-family: sans-serif; text-align: center; padding: 50px;">
                <h1>Backtest UI - Build Required</h1>
                <p>Run <code>npm run build</code> in the <code>ui</code> directory.</p>
            </body>
            </html>
            """
            webview.create_window('Backtest UI', html=html_content, js_api=self.api, width=1280, height=800)
        else:
            webview.create_window('Backtest UI', url=os.path.join(ui_dir, 'index.html'), js_api=self.api, width=1280, height=800)

        webview.start(debug=self.debug)
