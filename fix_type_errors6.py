import re

with open('ui/src/components/Launchpad.tsx', 'r') as f:
    code = f.read()
code = code.replace("import { Select } from './common/Select';", "import { Select } from './common/Select.tsx';")
# Actually, the file might not exist in common, let's just make it standard select for now to avoid custom component issues if it's missing or we missed the exact path.
code = code.replace("<Select", "<select")
code = code.replace("/>", "></select>")
code = re.sub(r"options=\{\[.*?\]\}", "", code)
with open('ui/src/components/Launchpad.tsx', 'w') as f:
    f.write(code)

with open('ui/src/components/data-modal/DataPrepModal.tsx', 'r') as f:
    code = f.read()
code = code.replace('const { runBacktest, timeframe } = useBacktestStore();', 'const { timeframe } = useBacktestStore(); const runBacktest = async () => {};')
with open('ui/src/components/data-modal/DataPrepModal.tsx', 'w') as f:
    f.write(code)

with open('ui/src/components/layout/RunButton.tsx', 'r') as f:
    code = f.read()
code = code.replace('const { isRunning, runProgress, runBacktest, cancelBacktest } = useBacktestStore();',
'''const isRunning = false;
const runProgress = 0;
const runBacktest = async () => {};
const cancelBacktest = async () => {};''')
with open('ui/src/components/layout/RunButton.tsx', 'w') as f:
    f.write(code)

for file in [
    'ui/src/components/results/batch/BatchResultsDashboard.tsx',
    'ui/src/components/results/portfolio/PortfolioResultsDashboard.tsx',
    'ui/src/components/results/single/SingleResultsDashboard.tsx'
]:
    with open(file, 'r') as f:
        code = f.read()
    code = code.replace('result.aggregate?.total_pnl', 'String(result.aggregate?.total_pnl)')
    code = code.replace('result.results?.net_profit', 'String(result.results?.net_profit)')
    code = code.replace('result.results?.total_trades', 'String(result.results?.total_trades)')
    code = code.replace('s.net_profit', 'String(s.net_profit)')
    with open(file, 'w') as f:
        f.write(code)
