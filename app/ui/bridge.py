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
        # Determine strict path to UI assets
        # In dev, use ui/dist. In prod, use frozen path.
        if getattr(sys, 'frozen', False):
            base_dir = sys._MEIPASS
            ui_dir = os.path.join(base_dir, 'ui', 'dist')
        else:
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            ui_dir = os.path.join(base_dir, 'ui', 'dist')

        # If ui/dist doesn't exist (Sprint 1), use a simple HTML string or file
        if not os.path.exists(ui_dir):
            print(f"UI directory not found at {ui_dir}. Using placeholder.")
            html_content = """
            <!DOCTYPE html>
            <html>
            <body>
                <h1>Backtest UI - Sprint 1</h1>
                <p>Bridge initialized.</p>
                <button onclick="testEcho()">Test Bridge</button>
                <div id="output"></div>
                <script>
                    async function testEcho() {
                        const res = await window.pywebview.api.echo('Hello from JS');
                        document.getElementById('output').innerText = res;
                    }
                </script>
            </body>
            </html>
            """
            webview.create_window(
                'Backtest UI', 
                html=html_content, 
                js_api=self.api,
                width=1280,
                height=800
            )
        else:
            webview.create_window(
                'Backtest UI', 
                url=os.path.join(ui_dir, 'index.html'), 
                js_api=self.api,
                width=1280,
                height=800
            )

        webview.start(debug=self.debug)
