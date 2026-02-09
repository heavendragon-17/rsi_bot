# Lessons Learned

> **For AI Agents** | Gotchas, bugs, and workarounds discovered during development

---

## 🔴 Critical Issues

### 1. Vite Base Path (CRITICAL)

**Problem:** By default, Vite uses absolute paths (`/assets/...`) which don't work with PyWebView's `file://` protocol.

**Error:** Assets fail to load when running `python main_ui.py`

**Solution:** Add `base: './'` to vite.config.ts:
```typescript
export default defineConfig({
    // ... other config
    base: './',  // REQUIRED for PyWebView
})
```

**Verification:** After `npm run build`, check `ui/dist/index.html` has relative paths:
```html
<script type="module" src="./assets/index-abc123.js"></script>
```

---

### 2. react-is Dependency (CRITICAL)

**Problem:** `recharts` package requires `react-is` as a peer dependency but doesn't install it automatically.

**Error:** Build fails with `Cannot find module 'react-is'`

**Solution:** Install explicitly:
```bash
npm install --legacy-peer-deps react-is
```

---

### 3. PyWebView Not Found

**Problem:** `ModuleNotFoundError: No module named 'webview'`

**Solution:** Install pywebview in your conda/venv:
```bash
pip install pywebview
```

---

## ⚠️ Important Gotchas

### 4. Path Resolution in Bridge

**Context:** The bridge.py needs to find UI assets correctly in both dev and prod.

**Pattern:**
```python
if getattr(sys, 'frozen', False):
    # Running as PyInstaller bundle
    base_dir = sys._MEIPASS
else:
    # Running as script
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ui_dir = os.path.join(base_dir, 'ui', 'dist')
```

---

### 5. Tailwind CSS v4 - No Config File

**Problem:** Tailwind v4 uses CSS-first configuration, no `tailwind.config.js`.

**Solution:** Configure via CSS:
```css
@import "tailwindcss";

@theme {
  --color-primary: #3b82f6;
}
```

---

### 6. npm Peer Dependency Conflicts

**Problem:** Some packages have conflicting peer dependencies.

**Solution:** Use `--legacy-peer-deps` flag:
```bash
npm install --legacy-peer-deps
```

---

### 7. SQLite Decimal Precision

**Problem:** SQLite REAL type loses decimal precision.

**Solution:** Store as TEXT, use Python Decimal:
```python
from decimal import Decimal

# Save
value = Decimal("1234.56789")
db.execute("INSERT INTO ... VALUES (?)", [str(value)])

# Load
row = db.fetchone()
value = Decimal(row['total_profit'])
```

---

### 8. Strategy Config - Never Edit .py Files

**Problem:** Editing strategy .py files from UI is dangerous.

**Solution:** Use JSON override files:
- Store overrides in `config/strategy_overrides/{strategy}.json`
- Load base config from DEFAULT_CONFIG in .py file
- Merge with JSON overrides if present

---

### 9. Timeseries Data Size

**Problem:** Equity curves can be very large, slowing down list views.

**Solution:** 
1. Compress with zlib before storing
2. NEVER fetch in list views
3. Only fetch when user clicks to view details

---

### 10. PowerShell vs CMD

**Problem:** Command chaining syntax differs between shells.

**PowerShell:** Use semicolon `;`
```powershell
cd ui; npm run build
```

**CMD/Bash:** Use `&&`
```bash
cd ui && npm run build
```

---

## 🧪 Debug Tips

### Enable PyWebView Debug Mode
```python
webview.start(debug=True)
```
Opens Chrome DevTools for frontend debugging.

### Test API Without UI
```python
from app.ui.api import BridgeAPI
api = BridgeAPI()
print(api.get_strategies())
```

### Test UI Initialization
```bash
python main_ui.py --test
```
Initializes without launching window.

---

## 📁 Folder Structure Clarifications

| Folder | Purpose | Status |
|--------|---------|--------|
| `ui/` | React frontend (root level) | Create this |
| `app/ui/` | Python bridge code | Create this |
| `app/ui_bridge/` | Legacy, unused | Ignore/delete |
| `Designstrategycommandcenter/` | Figma reference | Read-only |
