import re

with open('main.tex', encoding='utf-8') as f:
    content = f.read()
with open('generated_numbers.tex', encoding='utf-8') as f:
    nums = f.read()

used = set(re.findall(r'\\([a-zA-Z]{4,})', content))
defined = set(re.findall(r'\\newcommand[{]\\([^}]+)[}]', nums))

keywords = ['return','sharpe','vol','drawdown','calmar','turnover','sortino',
            'net','hrp','herc','global','improved','convex','defensive',
            'walkforward','frozen','cost','breakeven','eval','months','data',
            'etf','rebal','cvar','riskfree','aligned']

candidates = set()
for m in used:
    if m not in defined:
        ml = m.lower()
        if any(k in ml for k in keywords):
            candidates.add(m)

print('Likely undefined data macros:')
for m in sorted(candidates):
    print(' ', m)

print()
print('All defined:')
for m in sorted(defined):
    print(' ', m)
