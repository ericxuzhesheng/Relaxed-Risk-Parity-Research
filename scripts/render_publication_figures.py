"""Render publication figures from saved results; never rerun or alter backtests.

Chart contract: seven-model daily paths (2102 observations), scalar comparisons,
four frequency settings, and all weekly ETF targets. Use a fixed colorblind-safe
model palette with line-style redundancy, honest linear scales, and vector PDF
plus 300-dpi PNG. Full-resolution weekly tables accompany dense heatmaps.
"""
from pathlib import Path
import sys
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import PercentFormatter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.public_labels import PUBLICATION_MODELS, validate_publication_models

COLORS = ["#B53B4A", "#194F7D", "#528BB5", "#7C2036", "#DB8790", "#687887", "#92B6D0"]
STYLES = ["-", "--", "-.", ":", (0,(5,2,1,2)), (0,(3,1)), (0,(1,1))]
OUT = ROOT / "results/figures"


def style():
    plt.rcParams.update({"font.family": "sans-serif", "font.sans-serif": ["Arial", "Microsoft YaHei"],
        "font.size": 10, "axes.labelsize": 10, "axes.titlesize": 11, "axes.titleweight": "semibold",
        "axes.spines.top": False, "axes.spines.right": False, "axes.edgecolor": "#A0A7AF",
        "axes.linewidth": .6, "xtick.labelsize": 9, "ytick.labelsize": 9,
        "grid.color": "#E5E9ED", "grid.linewidth": .5, "legend.frameon": False,
        "pdf.fonttype": 42, "ps.fonttype": 42, "savefig.dpi": 300, "axes.unicode_minus": False})


def save(fig, name):
    fig.savefig(OUT / (name+".png"), dpi=300, bbox_inches="tight", facecolor="white")
    fig.savefig(OUT / (name+".pdf"), bbox_inches="tight", facecolor="white")
    plt.close(fig)


def paths(summary):
    for kind in ["nav", "drawdown"]:
        fig, ax = plt.subplots(figsize=(10.8, 5.5))
        for i, name in enumerate(PUBLICATION_MODELS):
            slug = name.lower().replace("/", "_").replace(" ", "_")
            d = pd.read_csv(ROOT / f"results/tables/comparison_{slug}_returns.csv", parse_dates=["date"])
            nav = (1+d.net_return).cumprod()
            value = nav if kind == "nav" else nav/nav.cummax()-1
            ax.plot(d.date, value, label=name, color=COLORS[i], linestyle=STYLES[i],
                    linewidth=2.0 if i == 0 else 1.1, zorder=10 if i==0 else 2, alpha=1 if i==0 else .86)
        ax.set_ylabel("Cumulative net value" if kind=="nav" else "Drawdown")
        ax.set_xlabel("Year")
        ax.grid(axis="y")
        ax.margins(x=.01)
        if kind=="drawdown": ax.yaxis.set_major_formatter(PercentFormatter(1,decimals=0))
        fig.legend(*ax.get_legend_handles_labels(), loc="lower center", ncol=2, fontsize=9,
                   bbox_to_anchor=(.5,.005), columnspacing=2.5, handlelength=3.3)
        fig.subplots_adjust(left=.09,right=.98,top=.97,bottom=.29)
        save(fig,"convex_adaptive_"+kind+"_comparison")


def scalars(summary):
    specs=[("avg_monthly_turnover","Average monthly turnover","convex_adaptive_turnover_comparison"),
           ("cvar_95_daily_loss","95% daily tail loss","convex_adaptive_cvar_comparison"),
           ("transaction_cost_drag","Annual return cost drag","convex_adaptive_transaction_cost_comparison")]
    data=summary.set_index("model").loc[list(PUBLICATION_MODELS)]
    for col,label,name in specs:
        fig,ax=plt.subplots(figsize=(10.8,4.2))
        y=np.arange(len(data)); vals=data[col].to_numpy()
        ax.hlines(y,0,vals,color="#DCE1E6",linewidth=2,zorder=1)
        ax.scatter(vals,y,c=COLORS,s=[65]+[42]*6,zorder=3,edgecolor="white",linewidth=.5)
        for i,v in enumerate(vals): ax.annotate(f"{v:.2%}",(v,i),xytext=(7,0),textcoords="offset points",va="center",fontsize=9)
        ax.set_yticks(y,list(data.index));ax.invert_yaxis();ax.set_xlabel(label)
        ax.xaxis.set_major_formatter(PercentFormatter(1));ax.set_xlim(0,max(vals)*1.22)
        ax.grid(axis="x");ax.spines['left'].set_visible(False);ax.tick_params(axis="y",length=0)
        fig.subplots_adjust(left=.36,right=.97,bottom=.16,top=.96)
        save(fig,name)


def frequency():
    d=pd.read_csv(ROOT/'results/tables/rebalance_frequency_sensitivity.csv').set_index('frequency_code').loc[['W','2W','M','Q']]
    fig,axes=plt.subplots(2,2,figsize=(10.8,6.1))
    for j,(ax,col,title) in enumerate(zip(axes.flat,['net_annual_return','sharpe_ratio','max_drawdown','avg_monthly_turnover'],['Net annual return','Sharpe (zero risk-free)','Maximum drawdown','Monthly turnover'])):
        vals=d[col].to_numpy();ax.bar(np.arange(4),vals,width=.54,color=[COLORS[0],COLORS[1],COLORS[2],COLORS[6]],zorder=3)
        ax.set_xticks(range(4),['Weekly','Biweekly','Monthly','Quarterly']);ax.set_title(f"({chr(97+j)})  {title}",loc='left',pad=12)
        ax.axhline(0,color='#A0A7AF',lw=.6);ax.grid(axis='y')
        lo=min(0,vals.min());hi=max(0,vals.max());span=hi-lo
        ax.set_ylim(lo-.2*span if lo<0 else 0,hi+.22*span)
        for k,v in enumerate(vals):ax.annotate(f'{v:.3f}' if col=='sharpe_ratio' else f'{v:.2%}',(k,v),xytext=(0,6 if v>=0 else -10),textcoords='offset points',ha='center',fontsize=9)
        if col!='sharpe_ratio':ax.yaxis.set_major_formatter(PercentFormatter(1,decimals=1))
    fig.tight_layout(pad=1.6,h_pad=2.7,w_pad=3)
    save(fig,'rebalance_frequency_sensitivity')


def weekly_weights():
    d=pd.read_csv(ROOT/'results/tables/primary_weekly_weights.csv',index_col=0,parse_dates=True)
    # Separate cash so it cannot suppress the contrast of all remaining holdings.
    fig,(a,b)=plt.subplots(2,1,figsize=(12,9),gridspec_kw={'height_ratios':[1,6]},sharex=True)
    cash=d['日利ETF'].to_numpy()
    a.plot(range(len(d)),cash,color=COLORS[0],lw=1.4)
    a.fill_between(range(len(d)),0,cash,color=COLORS[0],alpha=.10)
    a.set_ylim(0,1);a.yaxis.set_major_formatter(PercentFormatter(1));a.set_ylabel('Cash weight');a.grid(axis='y')
    a.set_title('(a)  Money-market ETF',loc='left')
    other=d.drop(columns='日利ETF')
    # Linear color scale is stated explicitly and shared by every non-cash asset.
    im=b.imshow(other.to_numpy().T,aspect='auto',interpolation='nearest',cmap='Blues',vmin=0,vmax=float(other.max().max()))
    b.set_yticks(range(len(other.columns)),other.columns,fontfamily='Microsoft YaHei',fontsize=8)
    b.set_title('(b)  Non-cash ETF weights',loc='left',pad=12)
    ticks=[i for i,date in enumerate(d.index) if i==0 or date.year!=d.index[i-1].year]
    b.set_xticks(ticks,[str(d.index[i].year) for i in ticks]);b.set_xlabel('Rebalance date')
    b.tick_params(axis='y',length=0)
    cb=fig.colorbar(im,ax=[a,b],fraction=.025,pad=.02);cb.ax.yaxis.set_major_formatter(PercentFormatter(1));cb.set_label('Target weight (linear scale)')
    fig.subplots_adjust(left=.17,right=.86,bottom=.07,top=.96,hspace=.28)
    save(fig,'primary_weights')


def correlation():
    d=pd.read_csv(ROOT/'results/tables/asset_graph_diagnostics.csv',parse_dates=['date'])
    d=d[d.date.ge('2018-01-02')]
    fig,axes=plt.subplots(3,1,figsize=(10.8,5.5),sharex=True)
    for j,(ax,col,label) in enumerate(zip(axes,['correlation_stress_score','avg_abs_corr','largest_cluster_size_ratio'],['Correlation stress','Mean absolute correlation','Largest cluster share'])):
        ax.plot(d.date,d[col],color=COLORS[j],lw=1.3);ax.set_ylabel(label,fontsize=9);ax.grid(axis='y')
        ax.set_ylim(0,max(1,float(d[col].max())*1.1))
    axes[-1].set_xlabel('Year');fig.tight_layout(h_pad=.8)
    save(fig,'asset_graph_stress_timeline')


def main():
    style();OUT.mkdir(exist_ok=True)
    s=pd.read_csv(ROOT/'results/tables/convex_adaptive_performance_summary.csv')
    validate_publication_models(s.model)
    paths(s);scalars(s);frequency();weekly_weights();correlation()
    print('Rendered all current publication figures as PNG and vector PDF')


if __name__=='__main__':main()
