"""Plot saved five-run LIBERO-LoHo cohorts; no model calls or run mutations."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
from matplotlib.lines import Line2D
from matplotlib.ticker import FuncFormatter, MaxNLocator
import numpy as np

WORKSPACE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WORKSPACE / "src"))
from loho_telemetry import read_attempt_journal, summarize_attempts

TASKS = (0, 1, 4)
MODELS = ("astra", "opus")
MODEL_IDS = {"astra": "gpt-6-astra", "opus": "claude-opus-5-5"}
LABELS = {"astra": "GPT-6 Astra max", "opus": "Opus 5.5 max"}
COLORS = {"astra": "#1f77b4", "opus": "#ff7f0e"}
METRICS = {
    "completion_percent": ("Goal completion score", "Completion (%)", 1, "percent"),
    "full_success_percent": ("Full-task success", "Success (%)", 1, "percent"),
    "total_tokens": ("Total tokens", "Tokens per run (millions)", 1e-6, "millions"),
    "estimated_api_cost_usd": ("Estimated API cost", "USD per run", 1, "usd"),
    "elapsed_seconds": ("Wall-clock time", "Minutes per run", 1 / 60, "minutes"),
    "total_api_latency_seconds": ("Cumulative API inference time", "Minutes per run", 1 / 60, "minutes"),
    "mean_api_latency_seconds": ("Mean API latency per call", "Seconds per call", 1, "seconds"),
    "api_calls": ("Model calls", "API calls per run", 1, "count"),
    "action_steps": ("Action steps", "Simulator action steps per run", 1, "count"),
}


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def gather():
    rows, source_files = [], {}
    for task in TASKS:
        folder = WORKSPACE / "loho-study" / ("task " + str(task))
        pointer_path = folder / ("latest_task{}_comparison.json".format(task))
        pointer = read_json(pointer_path)
        comparison_path = folder / pointer["comparison"]
        comparison = read_json(comparison_path)
        assert comparison["task_id"] == task and comparison["configuration_verified"]
        source_files[str(comparison_path.relative_to(WORKSPACE))] = hashlib.sha256(comparison_path.read_bytes()).hexdigest()
        for model in MODELS:
            cohort = next(item for item in comparison["models"] if item["model_id"] == MODEL_IDS[model])
            assert cohort["trials"] == len(cohort["episodes"]) == 5
            assert sorted(episode["trial"] for episode in cohort["episodes"]) == list(range(1, 6))
            for episode in cohort["episodes"]:
                directory = folder / episode["directory"]
                summary_path = directory / "summary.json"
                report = read_json(summary_path)
                verification = read_json(directory / "run_verification.json")
                digest = hashlib.sha256(summary_path.read_bytes()).hexdigest()
                assert verification["passed"] and verification["summary_sha256"] == digest
                assert report["task_id"] == task and report["model_id"] == MODEL_IDS[model]
                assert report["initial_state_id"] == report["sim_seed"] == 0
                assert report["max_decisions"] == 80 and report["max_action_steps"] == 2000
                assert report["effort"] == "max" and not report["cost_guard_enabled"]
                attempts, _ = read_attempt_journal(directory / "api_attempts.jsonl")
                telemetry = summarize_attempts(attempts)
                assert telemetry["cost_complete"] and telemetry["token_totals_complete"]
                assert telemetry["api_latency_totals_complete"]
                for name in ("total_input_tokens", "total_output_tokens", "estimated_api_cost_usd",
                             "total_api_latency_seconds", "mean_api_latency_seconds"):
                    assert report[name] == telemetry[name], (directory, name)
                rows.append({
                    "task_id": task, "model": model, "model_id": MODEL_IDS[model],
                    "display_trial": episode["trial"], "run_id": report["run_id"],
                    "source_summary": str(summary_path.relative_to(WORKSPACE)), "summary_sha256": digest,
                    "completion_percent": report["trial_score"]["completion_percent"],
                    "full_success_percent": 100.0 if report["success"] else 0.0,
                    "total_input_tokens": report["total_input_tokens"],
                    "total_output_tokens": report["total_output_tokens"],
                    "total_cached_input_tokens": report["total_cached_input_tokens"],
                    "total_cache_write_tokens": report["total_cache_write_tokens"],
                    "total_tokens": report["total_input_tokens"] + report["total_output_tokens"],
                    "estimated_api_cost_usd": report["estimated_api_cost_usd"],
                    "elapsed_seconds": report["elapsed_seconds"],
                    "total_api_latency_seconds": report["total_api_latency_seconds"],
                    "mean_api_latency_seconds": report["mean_api_latency_seconds"],
                    "api_calls": report["decisions_used"], "action_steps": report["simulator_action_steps"],
                    "termination_reason": report["termination_reason"],
                })
    assert len(rows) == len({row["run_id"] for row in rows}) == 30
    statistics = {}
    for key in METRICS:
        statistics[key] = {}
        for task in TASKS:
            statistics[key][str(task)] = {}
            for model in MODELS:
                values = np.array([row[key] for row in rows if row["task_id"] == task and row["model"] == model], dtype=float)
                assert len(values) == 5 and np.isfinite(values).all()
                statistics[key][str(task)][model] = {
                    "n": 5, "mean": float(values.mean()),
                    "sample_std": float(values.std(ddof=1)), "values": values.tolist(),
                }
    return rows, statistics, source_files


def label_number(value, kind):
    if kind == "usd":
        return "${:.2f}".format(value)
    if kind == "percent":
        return "{:.1f}%".format(value)
    if kind == "millions":
        return "{:.2f}M".format(value)
    return "{:.1f}".format(value)


def panel(ax, key, statistics):
    title, units, scale, kind = METRICS[key]
    positions = np.arange(len(TASKS), dtype=float)
    width = .31
    arrays = {}
    for model in MODELS:
        arrays[model] = (
            np.array([statistics[key][str(task)][model]["mean"] for task in TASKS]) * scale,
            np.array([statistics[key][str(task)][model]["sample_std"] for task in TASKS]) * scale,
        )
    highest = max(float(np.max(mean + std)) for mean, std in arrays.values())
    ceiling = max(highest * 1.22, 130 if kind == "percent" else .1)
    for model, offset in (("astra", -width / 2), ("opus", width / 2)):
        mean, std = arrays[model]
        bars = ax.bar(positions + offset, mean, width=width, color=COLORS[model],
                      yerr=std, linewidth=0, zorder=3,
                      error_kw={"ecolor": "#22272e", "elinewidth": 1.15,
                                "capsize": 4, "capthick": 1.15})
        for bar, average, spread in zip(bars, mean, std):
            ax.text(bar.get_x() + bar.get_width() / 2, average + spread + ceiling * .026,
                    label_number(average, kind), ha="center", va="bottom",
                    fontsize=10, color="#22272e", clip_on=False)
    ax.set_title(title, fontsize=14, fontweight="semibold", loc="left", pad=14, color="#1b2430")
    ax.set_ylabel(units, fontsize=10.5, labelpad=7)
    ax.set_xticks(positions)
    ax.set_xticklabels(["Task " + str(task) for task in TASKS], fontsize=11)
    ax.set_xlim(-.62, 2.62)
    ax.set_ylim(0, ceiling)
    ax.set_axisbelow(True)
    ax.yaxis.grid(True, color="#e2e6ea", linewidth=.75, linestyle=(0, (4, 4)))
    ax.tick_params(axis="both", length=0, pad=7, labelcolor="#404852")
    for spine in ax.spines.values():
        spine.set_color("#89919a")
        spine.set_linewidth(.65)
    if kind == "percent":
        ax.set_yticks([0, 25, 50, 75, 100, 125])
    else:
        ax.yaxis.set_major_locator(MaxNLocator(nbins=5))
    if kind == "usd":
        ax.yaxis.set_major_formatter(FuncFormatter(lambda value, _: "${:g}".format(value)))


def tokens_cost_panel(ax, statistics, encoding_legend=True):
    panel(ax, "total_tokens", statistics)
    ax.set_title("Total tokens and estimated API cost", fontsize=14, fontweight="semibold", loc="left", pad=14, color="#1b2430")
    price_axis = ax.twinx()
    highest = max(statistics["estimated_api_cost_usd"][str(task)][model]["mean"] +
                  statistics["estimated_api_cost_usd"][str(task)][model]["sample_std"]
                  for task in TASKS for model in MODELS)
    price_axis.set_ylim(0, highest * 1.30)
    price_axis.set_ylabel("Estimated API cost per run (USD)", fontsize=10.5, labelpad=10)
    price_axis.yaxis.set_major_locator(MaxNLocator(nbins=5))
    price_axis.yaxis.set_major_formatter(FuncFormatter(lambda value, _: "${:g}".format(value)))
    price_axis.tick_params(axis="y", length=0, pad=7, labelcolor="#404852")
    for name, spine in price_axis.spines.items():
        spine.set_visible(name == "right")
        spine.set_color("#89919a")
        spine.set_linewidth(.65)
    for model, offset in (("astra", -.155), ("opus", .155)):
        mean = [statistics["estimated_api_cost_usd"][str(task)][model]["mean"] for task in TASKS]
        std = [statistics["estimated_api_cost_usd"][str(task)][model]["sample_std"] for task in TASKS]
        outward = -.23 if model == "astra" else .23
        price_axis.errorbar(np.arange(3) + offset + outward, mean, yerr=std,
                            fmt="D", markersize=6.5, markerfacecolor="white",
                            markeredgecolor=COLORS[model], markeredgewidth=1.6,
                            ecolor=COLORS[model], elinewidth=1.2, capsize=3.5,
                            capthick=1.2, zorder=5)
    if encoding_legend:
        ax.legend(handles=[Patch(facecolor="#939aa3", label="Tokens: bars, left axis"),
                           Line2D([], [], marker="D", color="#404852", markerfacecolor="white",
                                  linestyle="none", label="Cost: diamonds, right axis")],
                  loc="upper left", frameon=False, fontsize=8.5, handlelength=1.4,
                  borderaxespad=.6)
    return price_axis


def legend(fig, top):
    handles = [Patch(facecolor=COLORS[model], label=LABELS[model]) for model in MODELS]
    fig.legend(handles=handles, loc="upper center", bbox_to_anchor=(.5, top),
               ncol=2, frameon=False, fontsize=12, handlelength=1.5, columnspacing=2.5)


def save(fig, destination, tight=True):
    for extension in ("png", "pdf", "svg"):
        export = destination.with_suffix("." + extension)
        fig.savefig(str(export), dpi=240, facecolor="white",
                    bbox_inches="tight" if tight else None, pad_inches=.22)
        if extension == "svg":
            export.write_text("\n".join(line.rstrip() for line in export.read_text(encoding="utf-8").splitlines())
                              + "\n", encoding="utf-8")
    plt.close(fig)


def readme_layout(fig, ax, heading):
    """Use one canvas and typography for the three figures displayed in the README."""
    fig.set_size_inches(9.3, 5.8)
    fig.subplots_adjust(left=.13, right=.88, top=.86, bottom=.22)
    ax.set_title("", loc="left")
    fig.suptitle(heading, fontsize=14, fontweight="semibold", y=.975, color="#1b2430")
    ax.tick_params(axis="both", labelsize=10, length=0, pad=7, labelcolor="#404852")
    ax.xaxis.label.set_size(10.5)
    ax.yaxis.label.set_size(10.5)


def readme_legend(fig, encoding=False):
    handles = [Patch(facecolor=COLORS[model], label=LABELS[model]) for model in MODELS]
    if encoding:
        handles = [handles[0], Patch(facecolor="#939aa3", label="Total tokens"), handles[1],
                   Line2D([], [], marker="D", color="#404852", markerfacecolor="white",
                          linestyle="none", label="Estimated API cost")]
    fig.legend(handles=handles, loc="lower center", bbox_to_anchor=(.5, .025),
               ncol=2, frameon=False, fontsize=12, handlelength=1.5, columnspacing=2.5)


def readme_figures(out, statistics):
    fig, ax = plt.subplots()
    panel(ax, "completion_percent", statistics)
    readme_layout(fig, ax, "Goal completion score")
    ax.tick_params(axis="x", labelsize=11)
    readme_legend(fig)
    save(fig, out / "completion_percent", tight=False)
    fig, ax = plt.subplots()
    tokens_cost_panel(ax, statistics, encoding_legend=False)
    readme_layout(fig, ax, "Total tokens and estimated API cost")
    ax.tick_params(axis="x", labelsize=11)
    readme_legend(fig, encoding=True)
    save(fig, out / "tokens_and_cost_tasks_0_1_4", tight=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--outdir", type=Path, default=WORKSPACE / "loho-study/plots")
    parser.add_argument("--only", choices=("readme",), help="Regenerate only the README completion and tokens/cost figures")
    args = parser.parse_args()
    out = args.outdir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10,
                         "svg.fonttype": "none", "pdf.fonttype": 42})
    rows, statistics, sources = gather()
    if args.only == "readme":
        previous = json.loads((out / "comparison_statistics.json").read_text(encoding="utf-8"))
        assert previous["source_comparison_sha256"] == sources
        assert previous["runs"] == rows and previous["statistics"] == statistics
        readme_figures(out, statistics)
        print(json.dumps({"runs": len(rows), "updated": ["completion_percent", "tokens_and_cost_tasks_0_1_4"]}))
        return
    data = {"created_at": datetime.now(timezone.utc).isoformat(), "n_per_task_model": 5,
            "std_definition": "Sample standard deviation across five independent run values, ddof=1; not SEM or a confidence interval.",
            "selection": "Current five saved runs per model in each task's latest result pointer; task 4 uses its retained run set.",
            "source_comparison_sha256": sources, "metric_definitions": {
                "completion_percent": "Equal-weight final native goal predicates, in percent.",
                "full_success_percent": "100 for native full-task success, otherwise 0; mean is full-success rate.",
                "total_tokens": "Provider-reported total input plus output across all requests per run. Includes cache reads/writes within input, once, and reported reasoning tokens within output. Repeated conversation context counts again when reported again.",
                "estimated_api_cost_usd": "Recorded per-run public-rate estimate using actual reported cache usage; USD.",
                "elapsed_seconds": "Recorded episode wall-clock duration; plotting units are minutes.",
                "total_api_latency_seconds": "Sum of request wall times per episode, including network and provider waiting; plotting units are minutes. This does not isolate model compute time.",
                "mean_api_latency_seconds": "Each run's mean request latency; bars average those five run means equally, not weighted by request count.",
                "api_calls": "Total API requests per run, including requests whose returned tools were rejected.",
                "action_steps": "Executed simulator control steps per run; excludes the five initial settling steps and API waiting.",
            }, "statistics": statistics, "runs": rows}
    (out / "comparison_statistics.json").write_text(json.dumps(data, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    keys = list(METRICS)
    fig, axes = plt.subplots(3, 1, figsize=(9.3, 13.5))
    fig.subplots_adjust(left=.13, right=.88, top=.83, bottom=.135, hspace=.60)
    fig.suptitle("LIBERO-LoHo | Astra vs Opus", fontsize=21, fontweight="semibold", y=.988, color="#1b2430")
    fig.text(.5, .948, "5 saved runs per model/task | mean ±1 sample SD", ha="center", fontsize=11, color="#555e69")
    legend(fig, .925)
    for ax, key in zip(axes.flat, ("completion_percent", "total_tokens", "elapsed_seconds")):
        if key == "total_tokens":
            tokens_cost_panel(ax, statistics)
        else:
            panel(ax, key, statistics)
    fig.text(.13, .045, "Tokens: input + output, including cache usage and reported reasoning.\n"
             "Whiskers: sample SD, not confidence intervals. Task 4: retained run set.\n"
             "All runs: state 0, seed 0, max effort, static + wrist RGB and proprioception.",
             fontsize=8.5, color="#626a73", linespacing=1.6)
    save(fig, out / "astra_opus_tasks_0_1_4")
    readme_figures(out, statistics)
    fig, axes = plt.subplots(1, 2, figsize=(14.4, 5.5))
    fig.subplots_adjust(left=.08, right=.98, top=.74, bottom=.18, wspace=.28)
    fig.suptitle("LIBERO-LoHo | Calls and action steps", fontsize=21, fontweight="semibold", y=.995, color="#1b2430")
    legend(fig, .91)
    for ax, key in zip(axes, ("api_calls", "action_steps")):
        panel(ax, key, statistics)
    fig.text(.08, .07, "5 saved runs per model/task | mean ±1 sample SD (ddof=1). Task 4: retained run set.", fontsize=10, color="#626a73")
    fig.text(.08, .025, "Calls include rejected returned tools. Action steps exclude initial settling and API waiting.", fontsize=9, color="#626a73")
    save(fig, out / "calls_and_steps_tasks_0_1_4")
    for key in keys:
        if key == "completion_percent":
            continue
        fig, ax = plt.subplots(figsize=(8.5, 5.5))
        fig.subplots_adjust(left=.13, right=.98, top=.79, bottom=.19)
        panel(ax, key, statistics)
        legend(fig, .98)
        fig.text(.13, .075, "5 saved runs per model/task | mean ±1 sample SD (ddof=1)", fontsize=9.5, color="#626a73")
        fig.text(.13, .035, "Task 4: retained run set. API latency includes network/provider waiting.", fontsize=8.5, color="#626a73")
        save(fig, out / key)
    lines = ["# Astra and Opus bar plots", "", "[Combined chart](astra_opus_tasks_0_1_4.png) · [PDF](astra_opus_tasks_0_1_4.pdf) · [SVG](astra_opus_tasks_0_1_4.svg)", "",
             "The main figure has one column: goal completion score, total tokens plus estimated API cost, and wall-clock time. In the middle panel, bars use the left token axis and white diamonds use the right USD axis; both have sample-SD whiskers.", "",
             "[Tokens and cost together](tokens_and_cost_tasks_0_1_4.png) · [PDF](tokens_and_cost_tasks_0_1_4.pdf) · [SVG](tokens_and_cost_tasks_0_1_4.svg)", "",
             "[Calls and action steps](calls_and_steps_tasks_0_1_4.png) · [PDF](calls_and_steps_tasks_0_1_4.pdf) · [SVG](calls_and_steps_tasks_0_1_4.svg)", "",
             "Blue is GPT-6 Astra max; orange is Opus 5.5 max. Each bar uses the mean of the current five saved runs for that task and model. Capped whiskers show plus/minus one sample standard deviation across those five run values (ddof=1). They are not standard errors or confidence intervals.", "",
             "Completion score measures final native goals; full success counts only runs with all goals satisfied. Percentage whiskers can extend above 100% because they show a descriptive standard deviation. Task 4 uses the current retained set. All thirty runs use stored state 0 and seed 0.", "",
             "Tokens are the sum of provider-reported input and output across requests, including cached context and reported reasoning. These are token volumes, not unique context lengths or tokens weighted by price. Costs use the run's recorded USD estimate with actual cache usage. Wall-clock is recorded episode duration; cumulative API time sums request latency, including network and provider waiting. Per-call latency averages the five run-level mean latencies equally. Calls include requests whose tools were rejected; action steps exclude the five initial settling steps and API waiting.", "",
             "| Metric | Task | Astra mean ± sample SD | Opus mean ± sample SD |", "|---|---|---:|---:|"]
    for key, (title, _, scale, kind) in METRICS.items():
        for task in TASKS:
            values = []
            for model in MODELS:
                item = statistics[key][str(task)][model]
                values.append("{} ± {}".format(label_number(item["mean"] * scale, kind), label_number(item["sample_std"] * scale, kind)))
            lines.append("| {} | {} | {} | {} |".format(title, task, *values))
    lines += ["", "Individual charts are available as PNG, PDF and SVG:", ""]
    for key, (title, _, _, _) in METRICS.items():
        lines.append("- [{}]({}.png) · [PDF]({}.pdf) · [SVG]({}.svg)".format(title, key, key, key))
    lines += ["", "[Exact statistics, per-run values and source hashes](comparison_statistics.json). Rebuild with `wsl -d Ubuntu-24.04 --exec /root/projects/LIBERO-LOHO/.venv/bin/python scripts/plot_study_comparison.py` from the workspace.", ""]
    if (out / "options/README.md").exists():
        lines += ["[Alternative figure and table gallery](options/README.md)", ""]
    (out / "README.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"outdir": str(out), "runs": len(rows), "combined_chart": "astra_opus_tasks_0_1_4.png",
                      "chart_count": 12, "formats": ["png", "pdf", "svg"],
                      "sample_std_ddof": 1}, indent=2))


if __name__ == "__main__":
    main()
