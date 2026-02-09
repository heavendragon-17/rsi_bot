import React, { useState, useEffect } from 'react';
import { Play, FileText, Settings, AlertCircle } from 'lucide-react';
import { useConfigStore } from '../stores/useConfigStore';
import { useDataStore } from '../stores/useDataStore';

const BacktestRunner: React.FC = () => {
    const { strategies, fetchStrategies } = useConfigStore();
    const { dataFiles, fetchDataFiles, fetchRuns } = useDataStore();
    
    const [selectedStrategy, setSelectedStrategy] = useState('');
    const [selectedFile, setSelectedFile] = useState('');
    const [initialBalance, setInitialBalance] = useState(10000);
    const [isRunning, setIsRunning] = useState(false);
    const [result, setResult] = useState<any>(null);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        fetchStrategies();
        fetchDataFiles();
    }, [fetchStrategies, fetchDataFiles]);

    // Set defaults when lists load
    useEffect(() => {
        if (strategies.length > 0 && !selectedStrategy) setSelectedStrategy(strategies[0].name);
        if (dataFiles.length > 0 && !selectedFile) setSelectedFile(dataFiles[0].path);
    }, [strategies, dataFiles]);

    const handleRun = async () => {
        setIsRunning(true);
        setError(null);
        setResult(null);

        try {
            if (window.pywebview) {
                const res = await window.pywebview.api.run_backtest({
                    strategy_name: selectedStrategy,
                    data_file: selectedFile,
                    initial_balance: initialBalance
                });

                if (res.success) {
                    setResult(res.data);
                    // Refresh history
                    fetchRuns();
                } else {
                    setError(res.error || 'Backtest failed');
                }
            } else {
                // Mock delay
                await new Promise(r => setTimeout(r, 2000));
                setResult({
                    run_id: 123,
                    metrics: {
                        net_profit_pct: 15.4,
                        win_rate: 0.65,
                        total_trades: 42
                    }
                });
            }
        } catch (err) {
            setError(String(err));
        } finally {
            setIsRunning(false);
        }
    };

    return (
        <div className="space-y-6">
            <div className="bg-[var(--bg-surface)] p-6 rounded-lg border border-[var(--border)] shadow-sm">
                <h3 className="text-lg font-bold mb-6 border-b border-[var(--border)] pb-2 flex items-center">
                    <Play className="w-5 h-5 mr-2 text-[var(--accent)]" />
                    Run Backtest
                </h3>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-6">
                    {/* Strategy Selection */}
                    <div className="space-y-2">
                        <label className="block text-sm font-medium text-[var(--text-secondary)]">Strategy</label>
                        <div className="relative">
                            <select 
                                value={selectedStrategy}
                                onChange={(e) => setSelectedStrategy(e.target.value)}
                                className="w-full pl-10 pr-4 py-2 bg-[var(--bg-surface)] border border-[var(--border)] rounded-md focus:ring-1 focus:ring-[var(--accent)] appearance-none"
                            >
                                {strategies.map(s => (
                                    <option key={s.name} value={s.name}>{s.display_name}</option>
                                ))}
                            </select>
                            <Settings className="w-4 h-4 absolute left-3 top-3 text-[var(--text-muted)]" />
                        </div>
                    </div>

                    {/* Data File Selection */}
                    <div className="space-y-2">
                        <label className="block text-sm font-medium text-[var(--text-secondary)]">Data File</label>
                        <div className="relative">
                            <select 
                                value={selectedFile}
                                onChange={(e) => setSelectedFile(e.target.value)}
                                className="w-full pl-10 pr-4 py-2 bg-[var(--bg-surface)] border border-[var(--border)] rounded-md focus:ring-1 focus:ring-[var(--accent)] appearance-none"
                            >
                                {dataFiles.length === 0 && <option value="">No CSV files found in /data</option>}
                                {dataFiles.map(f => (
                                    <option key={f.path} value={f.path}>
                                        {f.symbol} ({f.timeframe}) - {f.name}
                                    </option>
                                ))}
                            </select>
                            <FileText className="w-4 h-4 absolute left-3 top-3 text-[var(--text-muted)]" />
                        </div>
                    </div>

                    {/* Initial Balance */}
                    <div className="space-y-2">
                        <label className="block text-sm font-medium text-[var(--text-secondary)]">Initial Balance (USDT)</label>
                        <input 
                            type="number" 
                            value={initialBalance}
                            onChange={(e) => setInitialBalance(parseFloat(e.target.value))}
                            className="w-full px-4 py-2 bg-[var(--bg-surface)] border border-[var(--border)] rounded-md focus:ring-1 focus:ring-[var(--accent)]"
                        />
                    </div>
                </div>

                <div className="flex justify-end">
                    <button 
                        onClick={handleRun}
                        disabled={isRunning || !selectedStrategy || !selectedFile}
                        className={`
                            flex items-center space-x-2 px-8 py-3 rounded-md font-medium transition-all
                            ${isRunning 
                                ? 'bg-[var(--bg-secondary)] text-[var(--text-muted)] cursor-not-allowed' 
                                : 'bg-[var(--accent)] text-white hover:bg-[var(--accent-hover)] shadow-lg hover:shadow-xl'
                            }
                        `}
                    >
                        {isRunning ? (
                            <>
                                <div className="w-5 h-5 border-2 border-[var(--text-muted)] border-t-transparent rounded-full animate-spin"></div>
                                <span>Running...</span>
                            </>
                        ) : (
                            <>
                                <Play className="w-5 h-5 fill-current" />
                                <span>Start Backtest</span>
                            </>
                        )}
                    </button>
                </div>

                {/* Error Message */}
                {error && (
                    <div className="mt-6 p-4 bg-[var(--error)]/10 text-[var(--error)] rounded-md flex items-center">
                        <AlertCircle className="w-5 h-5 mr-2" />
                        {error}
                    </div>
                )}

                {/* Live/Quick Result */}
                {result && (
                    <div className="mt-6 p-4 bg-[var(--success)]/10 border border-[var(--success)]/20 rounded-md">
                        <h4 className="font-bold text-[var(--success)] mb-2">Backtest Completed!</h4>
                        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                            <div>
                                <span className="text-sm text-[var(--text-secondary)]">Net Profit</span>
                                <p className="text-lg font-bold">{result.metrics.net_profit_pct?.toFixed(2)}%</p>
                            </div>
                            <div>
                                <span className="text-sm text-[var(--text-secondary)]">Win Rate</span>
                                <p className="text-lg font-bold">{(result.metrics.win_rate * 100)?.toFixed(1)}%</p>
                            </div>
                            <div>
                                <span className="text-sm text-[var(--text-secondary)]">Trades</span>
                                <p className="text-lg font-bold">{result.metrics.total_trades}</p>
                            </div>
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
};

export default BacktestRunner;
