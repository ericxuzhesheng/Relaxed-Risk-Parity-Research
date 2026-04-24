import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
import os

plt.rcParams["font.sans-serif"] = ["SimHei"]
plt.rcParams["axes.unicode_minus"] = False

def plot_nav_comparison(nav_dict: dict, title: str, save_path: str):
    plt.figure(figsize=(12, 6))
    for name, nav in nav_dict.items():
        plt.plot(nav, label=name)
    plt.title(title)
    plt.legend()
    plt.grid(True)
    plt.savefig(save_path)
    plt.close()

def plot_weights(weights_df: pd.DataFrame, title: str, save_path: str):
    plt.figure(figsize=(12, 6))
    weights_df.plot.area(stacked=True, ax=plt.gca())
    plt.title(title)
    plt.legend(loc='center left', bbox_to_anchor=(1, 0.5))
    plt.tight_layout()
    plt.savefig(save_path)
    plt.close()

def plot_param_timeline(df: pd.DataFrame, param_col: str, title: str, save_path: str):
    plt.figure(figsize=(12, 4))
    plt.plot(df['date'], df[param_col], drawstyle='steps-post')
    plt.title(title)
    plt.savefig(save_path)
    plt.close()
