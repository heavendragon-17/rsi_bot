import { useState } from 'react';
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import { Play, Loader, AlertTriangle } from 'lucide-react';
import { useToast } from '../common/index';

interface SensitivityData {
  parameter: string;
  center: number;
  data: Array<{
    param_value: number;
    net_profit_pct: number;
    win_rate: number;
  }>;
}

export function SensitivityAnalysis() {
  const { addToast } = useToast();
  const [loading, setLoading] = useState(false);
  const [results, setResults] = useState<SensitivityData | null>(null);
  
  const [params, setParams] = useState({
    strategy_name: 'rsi_wma_retest',
    symbol: 'BTC/USDT',
    timeframe: '15m',
    param_name: 'rsi_period', // Default
    center_value: 14,
    step: 1,
    steps_count: 5
  });

  const handleRun = async () => {
    setLoading(true);
    try {
      if (window.pywebview) {
        const res = await window.pywebview.api.run_sensitivity(params);
        if (res.success) {
            setResults(res.data);
            addToast('success', 'Sensitivity analysis complete');
        } else {
            addToast('error', `Analysis failed: ${res.error}`);
        }
      } else {
        // Mock data for dev without backend
        addToast('info', 'Running in mock mode');
        setTimeout(() => {
            const mockData = [];
            for (let i = -5; i <= 5; i++) {
                const val = params.center_value + (i * params.step);
                mockData.push({
                    param_value: val,
                    net_profit_pct: 10 - Math.abs(i) * 0.5 + Math.random(),
                    win_rate: 60 - Math.abs(i) + Math.random() * 2
                });
            }
            setResults({
                parameter: params.param_name,
                center: params.center_value,
                data: mockData
            });
            setLoading(false);
        }, 1000);
        return;
      }
    } catch (e) {
      addToast('error', `Error: ${e}`);
    } finally {
        if (window.pywebview) setLoading(false);
    }
  };

  return (
    <div className="flex flex-col h-full gap-6">
       {/* Config Panel */}
       <div className="p-4 bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg">
          <h3 className="text-lg font-bold mb-4 flex items-center gap-2 text-[var(--color-text)]">
             <AlertTriangle size={20} className="text-yellow-500" />
             Sensitivity Analysis
          </h3>
          
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
             <div>
                <label className="block text-xs font-medium text-[var(--color-text-muted)] mb-1">Parameter</label>
                <select 
                   value={params.param_name}
                   onChange={e => setParams({...params, param_name: e.target.value})}
                   className="w-full p-2 bg-[var(--color-bg)] border border-[var(--color-border)] rounded text-[var(--color-text)]"
                >
                   <option value="rsi_period">RSI Period</option>
                   <option value="rsi_wma_length">WMA Length</option>
                   <option value="rsi_overbought">Overbought Level</option>
                   <option value="rsi_oversold">Oversold Level</option>
                </select>
             </div>
             <div>
                <label className="block text-xs font-medium text-[var(--color-text-muted)] mb-1">Center Value</label>
                <input 
                   type="number" 
                   value={params.center_value}
                   onChange={e => setParams({...params, center_value: parseFloat(e.target.value)})}
                   className="w-full p-2 bg-[var(--color-bg)] border border-[var(--color-border)] rounded text-[var(--color-text)]"
                />
             </div>
             <div>
                <label className="block text-xs font-medium text-[var(--color-text-muted)] mb-1">Step Size</label>
                <input 
                   type="number"
                   value={params.step}
                   onChange={e => setParams({...params, step: parseFloat(e.target.value)})}
                   className="w-full p-2 bg-[var(--color-bg)] border border-[var(--color-border)] rounded text-[var(--color-text)]"
                />
             </div>
          </div>
          
          <button 
             onClick={handleRun} 
             disabled={loading}
             className="flex items-center gap-2 px-6 py-2 bg-[var(--color-primary)] hover:bg-[var(--color-primary-hover)] text-white rounded font-medium disabled:opacity-50 transition-colors"
          >
             {loading ? <Loader className="animate-spin" size={18} /> : <Play size={18} />}
             Run Analysis
          </button>
       </div>

       {/* Results Chart */}
       {results && (
           <div className="flex-1 bg-[var(--color-surface)] border border-[var(--color-border)] rounded-lg p-6 min-h-[400px]">
              <h4 className="text-md font-semibold mb-4 text-[var(--color-text)]">
                 Impact of {results.parameter} on Net Profit %
              </h4>
              <ResponsiveContainer width="100%" height={350}>
                 <AreaChart data={results.data}>
                    <defs>
                       <linearGradient id="colorProfit" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="5%" stopColor="#2563eb" stopOpacity={0.3}/>
                          <stop offset="95%" stopColor="#2563eb" stopOpacity={0}/>
                       </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
                    <XAxis 
                        dataKey="param_value" 
                        stroke="var(--color-text-muted)"
                        tick={{fontSize: 12}}
                    />
                    <YAxis 
                        stroke="var(--color-text-muted)"
                        tick={{fontSize: 12}}
                    />
                    <Tooltip 
                        contentStyle={{
                            backgroundColor: 'var(--color-surface)',
                            borderColor: 'var(--color-border)',
                            color: 'var(--color-text)'
                        }}
                    />
                    <Area 
                        type="monotone" 
                        dataKey="net_profit_pct" 
                        stroke="#2563eb" 
                        fillOpacity={1} 
                        fill="url(#colorProfit)" 
                    />
                 </AreaChart>
              </ResponsiveContainer>
           </div>
       )}
    </div>
  );
}
