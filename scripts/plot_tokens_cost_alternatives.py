"""Export dot and scatter alternatives using the 30 saved study episodes."""
import json

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from matplotlib.ticker import FuncFormatter, MaxNLocator
import numpy as np

from plot_study_comparison import WORKSPACE, TASKS, MODELS, COLORS, LABELS, gather, save

OUT = WORKSPACE / "loho-study/plots/options/tokens_cost"


def style_axes(ax, grid):
    ax.set_axisbelow(True)
    ax.grid(axis=grid, color="#e2e6ea", linewidth=.75, linestyle=(0, (4, 4)))
    for name, spine in ax.spines.items():
        spine.set_visible(name in ("left", "bottom"))
        spine.set_color("#89919a")
        spine.set_linewidth(.65)
    ax.tick_params(length=0, pad=7, labelsize=10, labelcolor="#404852")
    ax.xaxis.label.set_size(10.5)
    ax.yaxis.label.set_size(10.5)


def bottom_legend(fig):
    # Matplotlib lays out legend entries by column, giving two coherent rows.
    handles = [Patch(facecolor=COLORS['astra'], label=LABELS['astra']),
               Line2D([], [], marker='o', color='#6e7781', linestyle='none', markersize=5,
                      label='Individual episode'),
               Patch(facecolor=COLORS['opus'], label=LABELS['opus']),
               Line2D([], [], marker='D', markerfacecolor='white', markeredgecolor='#30363d',
                      color='#30363d', markersize=7, label='Mean ± sample SD')]
    fig.legend(handles=handles, loc='lower center', bbox_to_anchor=(.5, .015), ncol=2,
               frameon=False, fontsize=12, handlelength=1.5, columnspacing=2.5)


def cohort(rows, task, model):
    return sorted((row for row in rows if row['task_id'] == task and row['model'] == model),
                  key=lambda row: row['display_trial'])


def dot_plot(rows, statistics):
    fig, axes = plt.subplots(1, 2, figsize=(12.8, 5.8), sharey=True)
    fig.subplots_adjust(left=.09, right=.98, top=.86, bottom=.26, wspace=.20)
    fig.suptitle('Total tokens and estimated API cost', y=.975, fontsize=14,
                 fontweight='semibold', color='#1b2430')
    panels = [('total_tokens', 1e-6, 'Total tokens per run (millions)'),
              ('estimated_api_cost_usd', 1, 'Estimated API cost per run (USD)')]
    for ax, (key, scale, units) in zip(axes, panels):
        highest = 0
        for task_index, task in enumerate(TASKS):
            for model_index, model in enumerate(MODELS):
                values = np.array([row[key] * scale for row in cohort(rows, task, model)])
                assert len(values) == 5
                y = task_index * 1.5 + (model_index - .5) * .46
                ax.scatter(values, y + np.linspace(-.075, .075, 5), color=COLORS[model],
                           s=35, alpha=.80, edgecolor='white', linewidth=.45, zorder=4)
                item = statistics[key][str(task)][model]
                mean, sd = item['mean'] * scale, item['sample_std'] * scale
                ax.errorbar(mean, y, xerr=sd, fmt='D', markersize=7,
                            markerfacecolor='white', markeredgecolor=COLORS[model], markeredgewidth=1.6,
                            ecolor=COLORS[model], elinewidth=1.3, capsize=4, capthick=1.3, zorder=5)
                highest = max(highest, mean + sd, float(values.max()))
        ax.set_xlabel(units)
        ax.set_xlim(0, highest * 1.10)
        ax.set_ylim(3.65, -.65)
        ax.set_yticks([i * 1.5 for i in range(3)])
        ax.set_yticklabels(['Task ' + str(task) for task in TASKS])
        ax.xaxis.set_major_locator(MaxNLocator(nbins=5))
        if key == 'estimated_api_cost_usd':
            ax.xaxis.set_major_formatter(FuncFormatter(lambda value, _: '${:g}'.format(value)))
        style_axes(ax, 'x')
        ax.tick_params(axis='y', labelsize=11)
    bottom_legend(fig)
    save(fig, OUT / '01_tokens_cost_dot_plot', tight=False)


def scatter_plot(rows, statistics):
    fig, axes = plt.subplots(1, 3, figsize=(12.8, 5.8), sharex=True, sharey=True)
    fig.subplots_adjust(left=.08, right=.985, top=.82, bottom=.29, wspace=.12)
    fig.suptitle('Token usage versus estimated API cost', y=.975, fontsize=14,
                 fontweight='semibold', color='#1b2430')
    max_tokens = max(row['total_tokens'] * 1e-6 for row in rows)
    max_cost = max(row['estimated_api_cost_usd'] for row in rows)
    for ax, task in zip(axes, TASKS):
        for model in MODELS:
            group = cohort(rows, task, model)
            x = [row['total_tokens'] * 1e-6 for row in group]
            y = [row['estimated_api_cost_usd'] for row in group]
            ax.scatter(x, y, color=COLORS[model], s=48, alpha=.85, edgecolor='white',
                       linewidth=.55, zorder=4)
            tokens = statistics['total_tokens'][str(task)][model]
            cost = statistics['estimated_api_cost_usd'][str(task)][model]
            ax.errorbar(tokens['mean'] * 1e-6, cost['mean'],
                        xerr=tokens['sample_std'] * 1e-6, yerr=cost['sample_std'],
                        fmt='D', markersize=7, markerfacecolor='white',
                        markeredgecolor=COLORS[model], markeredgewidth=1.6, ecolor=COLORS[model],
                        elinewidth=1.25, capsize=3.5, capthick=1.25, zorder=5)
            max_tokens = max(max_tokens, (tokens['mean'] + tokens['sample_std']) * 1e-6)
            max_cost = max(max_cost, cost['mean'] + cost['sample_std'])
        ax.set_title('Task ' + str(task), fontsize=11, fontweight='normal', color='#404852', pad=12)
        ax.xaxis.set_major_locator(MaxNLocator(nbins=4))
        ax.yaxis.set_major_locator(MaxNLocator(nbins=4))
        ax.yaxis.set_major_formatter(FuncFormatter(lambda value, _: '${:g}'.format(value)))
        style_axes(ax, 'both')
    axes[0].set_xlim(0, max_tokens * 1.10)
    axes[0].set_ylim(0, max_cost * 1.12)
    axes[0].set_ylabel('Estimated API cost per run (USD)')
    fig.supxlabel('Total tokens per run (millions)', y=.18, fontsize=10.5)
    bottom_legend(fig)
    save(fig, OUT / '02_tokens_cost_scatter', tight=False)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 10,
                         'svg.fonttype': 'none', 'pdf.fonttype': 42})
    rows, statistics, sources = gather()
    previous = json.loads((WORKSPACE / 'loho-study/plots/comparison_statistics.json').read_text())
    assert previous['runs'] == rows and previous['statistics'] == statistics
    assert previous['source_comparison_sha256'] == sources
    dot_plot(rows, statistics)
    scatter_plot(rows, statistics)
    provenance = {
        'passed': True, 'source_runs': len(rows), 'episodes_per_model_task': 5,
        'source_comparison_sha256': sources,
        'source_summaries': [{'file': r['source_summary'], 'sha256': r['summary_sha256']} for r in rows],
        'total_tokens_definition': previous['metric_definitions']['total_tokens'],
        'cost_definition': previous['metric_definitions']['estimated_api_cost_usd'],
        'std_definition': 'Sample SD across the five episodes, ddof=1; not SEM or a confidence interval.',
        'dot_jitter': 'Small deterministic vertical offsets separate episode dots; token and cost values are unchanged.',
        'scatter_whiskers': 'Horizontal and vertical whiskers are separate marginal sample SDs for tokens and cost.',
        'scatter_axes_shared_across_tasks': True,
        'cohort_statistics': {key: statistics[key] for key in ('total_tokens', 'estimated_api_cost_usd')},
    }
    (OUT / 'sources.json').write_text(json.dumps(provenance, indent=2) + '\n', encoding='utf-8')
    (OUT / 'README.md').write_text(
        '# Tokens and cost alternatives\n\n'
        '## Dot plot\n\n![Dot plot](01_tokens_cost_dot_plot.png)\n\n'
        'Compare the models separately on token volume and estimated cost. Small dots show each episode; '
        'white diamonds and whiskers show mean ± sample SD across five episodes per model/task.\n\n'
        '## Scatter plot\n\n![Scatter plot](02_tokens_cost_scatter.png)\n\n'
        'Each dot plots one episode\'s total token usage against estimated cost. Tasks share the same axis scales. '
        'White diamonds show cohort means, with separate sample-SD whiskers along each axis.\n\n'
        'Total tokens are input plus output, including reported reasoning and cache usage. '
        'These are token volumes, not output tokens alone. [Recorded values and source hashes](sources.json).\n\n'
        'Each figure also has PDF and SVG exports with the same filename stem. '
        'Rebuild from the repository root with '
        '`wsl -d Ubuntu-24.04 --exec /root/projects/LIBERO-LOHO/.venv/bin/python scripts/plot_tokens_cost_alternatives.py`.\n',
        encoding='utf-8')
    print(json.dumps({'outdir': str(OUT), 'episodes': len(rows), 'figures': 2, 'formats': ['png', 'pdf', 'svg']}))


if __name__ == '__main__':
    main()
