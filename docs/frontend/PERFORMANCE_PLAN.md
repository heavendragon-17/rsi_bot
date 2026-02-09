# Performance Plan - Frontend Optimization

> **Document Type:** Performance Strategy  
> **Agent:** performance-optimizer  
> **Status:** Phase 3 Documentation

---

## Context

PyWebView apps run in a local browser engine. While no network latency exists, we still need to optimize:

1. **Bundle size** - Affects initial load time
2. **Rendering** - Large data sets (trades, equity curves)
3. **Memory** - Long-running sessions

---

## 1. Bundle Optimization

### Current Estimated Bundle

| Library | Size (minified) |
|---------|-----------------|
| React + ReactDOM | ~45 KB |
| Zustand | ~3 KB |
| lightweight-charts | ~95 KB |
| framer-motion | ~60 KB |
| Tailwind (purged) | ~10 KB |
| App code | ~50 KB |
| **Total** | ~263 KB |

### Optimization Strategies

#### 1.1 Tree Shaking
```typescript
// ❌ Bad: Imports entire library
import * as charts from 'lightweight-charts';

// ✅ Good: Import only what's needed
import { createChart, LineData } from 'lightweight-charts';
```

#### 1.2 Code Splitting (Not Recommended for Local)
For PyWebView, single bundle is preferred:
- No network fetch overhead for chunks
- Simpler deployment (`dist/` folder)
- Predictable loading

#### 1.3 Minification
Vite handles this automatically in production build:
```bash
npm run build  # Uses terser for minification
```

---

## 2. Rendering Optimization

### 2.1 Virtualized Lists

For trades table (potentially 1000+ rows):

```typescript
// ui/src/components/TradesTable.tsx
import { useVirtualizer } from '@tanstack/react-virtual';

function TradesTable({ trades }: { trades: Trade[] }) {
  const parentRef = useRef<HTMLDivElement>(null);
  
  const virtualizer = useVirtualizer({
    count: trades.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => 40,  // Row height
    overscan: 10
  });
  
  return (
    <div ref={parentRef} className="h-[400px] overflow-auto">
      <div style={{ height: virtualizer.getTotalSize() }}>
        {virtualizer.getVirtualItems().map((virtualRow) => (
          <TradeRow key={virtualRow.key} trade={trades[virtualRow.index]} />
        ))}
      </div>
    </div>
  );
}
```

### 2.2 Memoization

```typescript
// Memoize expensive components
const MetricsCards = React.memo(({ metrics }: Props) => {
  // ...
});

// Memoize computed values
const sortedTrades = useMemo(() => {
  return [...trades].sort((a, b) => {
    if (sortBy === 'pnl') return b.pnl - a.pnl;
    return new Date(b.entry_time) - new Date(a.entry_time);
  });
}, [trades, sortBy]);
```

### 2.3 Lazy Loading Charts

```typescript
// Only render chart when visible
import { useInView } from 'react-intersection-observer';

function EquityChartSection({ run_id }: { run_id: number }) {
  const { ref, inView } = useInView({ triggerOnce: true });
  
  return (
    <div ref={ref}>
      {inView ? (
        <EquityChart run_id={run_id} />
      ) : (
        <div className="h-[300px] bg-gray-800 animate-pulse" />
      )}
    </div>
  );
}
```

---

## 3. Data Optimization

### 3.1 Lazy Load Time-series

```typescript
// Dashboard shows preview (100 points)
const results = await api.run_backtest(params);
// results.equity_preview = first 100 points

// Full data only on chart interaction
const handleChartExpand = async () => {
  const fullData = await api.get_run_timeseries(run_id);
  setEquityCurve(fullData.equity_curve);
};
```

### 3.2 Pagination

```typescript
// Trades table pagination
const PAGE_SIZE = 50;

function usePaginatedTrades(run_id: number) {
  const [page, setPage] = useState(0);
  const [trades, setTrades] = useState<Trade[]>([]);
  
  useEffect(() => {
    api.get_trades(run_id, {
      limit: PAGE_SIZE,
      offset: page * PAGE_SIZE
    }).then(setTrades);
  }, [run_id, page]);
  
  return { trades, page, setPage };
}
```

### 3.3 Debounce Filter Changes

```typescript
// Don't refetch on every keystroke
import { useDebouncedCallback } from 'use-debounce';

function HistoryFilters() {
  const [input, setInput] = useState('');
  
  const debouncedSetFilter = useDebouncedCallback(
    (value) => useHistoryStore.getState().setFilters({ symbol: value }),
    300
  );
  
  return (
    <input
      value={input}
      onChange={(e) => {
        setInput(e.target.value);
        debouncedSetFilter(e.target.value);
      }}
    />
  );
}
```

---

## 4. Memory Management

### 4.1 Cleanup on Unmount

```typescript
// Clear large data when leaving page
useEffect(() => {
  return () => {
    useBacktestStore.getState().clearResults();
  };
}, []);
```

### 4.2 Chart Disposal

```typescript
// lightweight-charts requires explicit cleanup
useEffect(() => {
  const chart = createChart(containerRef.current, options);
  
  return () => {
    chart.remove();  // Important for memory
  };
}, []);
```

### 4.3 Limit History in Memory

```typescript
// Keep only recent runs in memory
const MAX_RUNS_IN_MEMORY = 100;

const loadRuns = async () => {
  const runs = await api.get_run_history({ limit: MAX_RUNS_IN_MEMORY });
  set({ runs });
};
```

---

## 5. Loading States

### 5.1 Skeleton Screens

```typescript
// Show structure while loading
function MetricsCardsSkeleton() {
  return (
    <div className="grid grid-cols-4 gap-4">
      {[...Array(4)].map((_, i) => (
        <div key={i} className="h-24 bg-gray-800 rounded animate-pulse" />
      ))}
    </div>
  );
}

function DashboardPage() {
  const { isRunning, results } = useBacktestStore();
  
  if (isRunning) return <MetricsCardsSkeleton />;
  if (results) return <MetricsCards metrics={results.metrics} />;
  return <EmptyState />;
}
```

### 5.2 Progress Indicator

```typescript
// Show progress during backtest
function BacktestProgress({ progress }: { progress: number }) {
  return (
    <div className="relative h-2 bg-gray-700 rounded-full overflow-hidden">
      <div
        className="absolute h-full bg-green-500 transition-all duration-300"
        style={{ width: `${progress}%` }}
      />
    </div>
  );
}
```

---

## 6. Benchmarks & Targets

| Metric | Target | Measurement |
|--------|--------|-------------|
| Initial load | < 500ms | Time to interactive |
| Backtest display | < 100ms | Results render time |
| Chart render | < 200ms | Equity curve display |
| Trades scroll | 60 FPS | Virtualized list FPS |
| Memory (idle) | < 100 MB | Heap size |
| Memory (1000 trades) | < 150 MB | Heap with data |

### Measuring

```typescript
// Add performance marks
performance.mark('backtest-start');

const results = await api.run_backtest(params);

performance.mark('backtest-end');
performance.measure('backtest-duration', 'backtest-start', 'backtest-end');

const duration = performance.getEntriesByName('backtest-duration')[0].duration;
console.log(`Backtest completed in ${duration}ms`);
```

---

## 7. Dependencies to Add

```json
{
  "dependencies": {
    "@tanstack/react-virtual": "^3.0.0",    // Virtualized lists
    "react-intersection-observer": "^9.0.0"  // Lazy loading
  },
  "devDependencies": {
    "vite-plugin-compression": "^0.5.0"      // Gzip assets
  }
}
```

---

## 8. Build Configuration

```typescript
// ui/vite.config.ts
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import compression from 'vite-plugin-compression';

export default defineConfig({
  plugins: [
    react(),
    compression({ algorithm: 'gzip' })
  ],
  build: {
    target: 'esnext',
    minify: 'terser',
    rollupOptions: {
      output: {
        // Keep single bundle for local app
        manualChunks: undefined
      }
    }
  }
});
```

---

## Cross-Reference

| Document | Purpose |
|----------|---------|
| [COMPONENT_MANIFEST.md](./COMPONENT_MANIFEST.md) | Components to optimize |
| [API_CONTRACTS.md](../backend/API_CONTRACTS.md) | Lazy load patterns |
