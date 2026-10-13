"""Create publication figure options from the 30 current saved study runs."""
import argparse
import json
from pathlib import Path
import statistics

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
from matplotlib.lines import Line2D
from matplotlib.ticker import FuncFormatter, MaxNLocator
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from plot_study_comparison import (WORKSPACE, TASKS, MODELS, COLORS, gather,
                                   readme_layout, readme_legend, save as save_readme)

OUT = WORKSPACE / "loho-study/plots/options"
NAMES = {"astra": "Astra", "opus": "Opus"}
TASK_NAMES = {0: "Drawer", 1: "Basket", 4: "Drawer + bowl"}
FIGURES = []
RECORDS = []
METRICS = (
    ("completion_percent", "Goal completion", "%", 1),
    ("total_output_tokens", "Output tokens", "Thousands per run", .001),
    ("estimated_api_cost_usd", "Estimated API cost", "USD per run", 1),
    ("elapsed_seconds", "Wall-clock time", "Minutes per run", 1 / 60),
)


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def cohort(task, model):
    return sorted((row for row in RECORDS if row["task_id"] == task and row["model"] == model), key=lambda row: row["display_trial"])


def stats(task, model, key, scale=1):
    values = [row[key] * scale for row in cohort(task, model)]
    assert len(values) == 5
    return statistics.mean(values), statistics.stdev(values)


def axes_style(ax, grid="y"):
    ax.set_axisbelow(True)
    ax.grid(axis=grid, color="#e2e6ea", linewidth=.7, linestyle=(0, (4, 4)))
    for name, spine in ax.spines.items():
        spine.set_visible(name in ("left", "bottom"))
        spine.set_color("#9aa2ab")
        spine.set_linewidth(.7)
    ax.tick_params(length=0, pad=6, labelcolor="#424b57")


def legend(fig, y=.92, extra=None):
    handles = [Patch(facecolor=COLORS[model], label=NAMES[model]) for model in MODELS]
    if extra:
        handles += extra
    y = min(y, getattr(fig, "_option_legend_y", y))
    fig.legend(handles=handles, loc="upper center", bbox_to_anchor=(.5, y), ncol=len(handles),
               frameon=False, fontsize=10, columnspacing=2, handlelength=1.3)


def title(fig, number, heading, subtitle):
    fig.suptitle("{} | {}".format(number, heading), y=.986, fontsize=21, fontweight="semibold", color="#1b2430")
    subtitle_y = .986 - 44 / (fig.get_figheight() * 72)
    fig._option_legend_y = subtitle_y - 10 / (fig.get_figheight() * 72)
    fig.text(.5, subtitle_y, subtitle, ha="center", fontsize=10.5, color="#5e6875")


def footer(fig, text, y=.035):
    fig.text(.075, y, text, fontsize=9, color="#626d7a", linespacing=1.45)


def save(fig, name, heading, description, primary=True):
    for extension in ("png", "pdf", "svg"):
        destination = OUT / (name + "." + extension)
        fig.savefig(str(destination), dpi=220, facecolor="white", bbox_inches="tight", pad_inches=.22)
        if extension == "svg":
            destination.write_text("\n".join(line.rstrip() for line in destination.read_text(encoding="utf-8").splitlines())
                                   + "\n", encoding="utf-8")
    plt.close(fig)
    FIGURES.append({"file": name + ".png", "title": heading, "description": description, "primary": primary})
    print("SAVED " + name, flush=True)


def individual_dots():
    fig, axes = plt.subplots(2, 2, figsize=(13.4, 10))
    fig.subplots_adjust(left=.075, right=.98, top=.84, bottom=.12, hspace=.42, wspace=.25)
    title(fig, 1, "Every run, plus mean and variability", "Five saved runs per model and task; each circle is one episode")
    legend(fig, .912, [Line2D([], [], marker="D", linestyle="none", color="#333a44", markerfacecolor="white", label="Mean ± sample SD")])
    for ax, (key, heading, units, scale) in zip(axes.flat, METRICS):
        max_y = 0
        for task_index, task in enumerate(TASKS):
            for model, shift in (("astra", -.20), ("opus", .20)):
                values = [row[key] * scale for row in cohort(task, model)]
                x = task_index + shift
                ax.scatter(x + np.linspace(-.065, .065, 5), values, s=43, color=COLORS[model], alpha=.85, zorder=4)
                mean, sd = stats(task, model, key, scale)
                ax.errorbar(x + .105, mean, yerr=sd, fmt="D", markersize=6,
                            markerfacecolor="white", markeredgecolor=COLORS[model], markeredgewidth=1.5,
                            ecolor=COLORS[model], capsize=4, elinewidth=1.2, zorder=5)
                max_y = max(max_y, mean + sd, max(values))
        ax.set_title(heading, fontsize=14, loc="left", fontweight="semibold", pad=12)
        ax.set_ylabel(units)
        ax.set_xticks(range(3))
        ax.set_xticklabels(["Task " + str(task) for task in TASKS])
        ax.set_xlim(-.5, 2.6)
        ax.set_ylim(0, max(125 if key == "completion_percent" else 0, max_y * 1.12))
        axes_style(ax)
        if key == "estimated_api_cost_usd":
            ax.yaxis.set_major_formatter(FuncFormatter(lambda value, _: "${:g}".format(value)))
    footer(fig, "Output tokens include reasoning; wall-clock includes API requests. Whiskers are sample SD (ddof=1), not confidence intervals.\nTask 4 uses the current retained run set; state 0 and seed 0 throughout.")
    save(fig, "01_individual_run_dots", "Individual-run dot plots", "Best for seeing all five observations, their variability and outliers across the four headline metrics.")


def time_breakdown():
    fig, ax = plt.subplots()
    bar_height = .74
    for task_index, task in enumerate(TASKS):
        for model_index, model in enumerate(MODELS):
            y = task_index * 2.8 + (model_index - .5) * bar_height
            mean, sd = stats(task, model, "total_api_latency_seconds", 1 / 60)
            ax.barh(y, mean, height=bar_height, color=COLORS[model], linewidth=0,
                    antialiased=False, zorder=3)
            ax.errorbar(mean, y, xerr=sd, fmt="none", color="#242a33", capsize=4, elinewidth=1.15, zorder=5)
            ax.text(mean + sd + .6, y, "{:.1f} ± {:.1f}".format(mean, sd), va="center", fontsize=10)
    locations = [task_index * 2.8 for task_index in range(3)]
    ax.set_yticks(locations)
    ax.set_yticklabels(["Task {}".format(task) for task in TASKS], fontweight="normal")
    ax.invert_yaxis()
    ax.set_xlim(0, 63)
    ax.set_xlabel("API request time per run (minutes)")
    axes_style(ax, "x")
    readme_layout(fig, ax, "API request time")
    ax.tick_params(axis="y", labelsize=11)
    readme_legend(fig)
    save_readme(fig, OUT / "02_wallclock_breakdown", tight=False)
    FIGURES.append({"file": "02_wallclock_breakdown.png", "title": "API request time",
                    "description": "Compares measured API request time per episode, with mean and sample SD; other episode time is excluded.",
                    "primary": True})
    print("SAVED 02_wallclock_breakdown", flush=True)


def progress_curves():
    fig, axes = plt.subplots(1, 3, figsize=(16.2, 6.3), sharey=True)
    fig.subplots_adjust(left=.065, right=.985, top=.76, bottom=.22, wspace=.17)
    title(fig, 3, "How goal completion develops", "Thin lines show all five runs; thick lines show a successful example closest to the cohort median wall time")
    legend(fig, .899)
    for ax, task in zip(axes, TASKS):
        for model in MODELS:
            rows = cohort(task, model)
            median = statistics.median(row["elapsed_seconds"] for row in rows)
            example = min((row for row in rows if row["full_success_percent"] == 100), key=lambda row:abs(row["elapsed_seconds"] - median))
            for row in rows:
                report = read_json(WORKSPACE / row["source_summary"])
                x, y, steps = [0], [report["trial_score"]["initial_completion_percent"]], 0
                for decision in report["decisions"]:
                    steps += decision["executed_steps"]
                    if decision.get("private_trial_score", {}).get("available"):
                        x.append(steps)
                        y.append(decision["private_trial_score"]["completion_percent"])
                assert steps == row["action_steps"]
                if x[-1] != steps or y[-1] != row["completion_percent"]:
                    x.append(steps)
                    y.append(row["completion_percent"])
                highlight = row["run_id"] == example["run_id"]
                ax.step(x, y, where="post", color=COLORS[model], linewidth=2.3 if highlight else 1,
                        alpha=1 if highlight else .27, zorder=4 if highlight else 2)
                ax.scatter(x[-1], y[-1], s=32 if highlight else 17, color=COLORS[model], alpha=1 if highlight else .6, zorder=5)
        ax.set_title("Task {} | {}".format(task, TASK_NAMES[task]), loc="left", fontsize=13, fontweight="semibold", pad=12)
        ax.set_xlabel("Executed action steps")
        ax.set_ylim(-3, 110)
        ax.set_yticks([0, 25, 50, 75, 100])
        axes_style(ax)
    axes[0].set_ylabel("Observed goal completion (%)")
    footer(fig, "Scores are sampled at decision ends; stair-step transitions show when a condition was observed, not its exact onset.\nAction-step axes omit API waiting and therefore describe physical progress, not wall-clock speed. Task 4: retained run set.")
    save(fig, "03_goal_progress_curves", "Goal-progress curves", "Shows observed subtask progress, recoveries and final partial outcomes against executed action steps.")


def cost_completion():
    fig, axes = plt.subplots(1, 3, figsize=(15.7, 6.2), sharey=True)
    fig.subplots_adjust(left=.07, right=.985, top=.77, bottom=.20, wspace=.15)
    title(fig, 4, "Cost and completion for each episode", "Each point is one saved run; nearby numbers identify run 1–5")
    legend(fig, .899)
    for ax, task in zip(axes, TASKS):
        for model in MODELS:
            for index, row in enumerate(cohort(task, model)):
                ax.scatter(row["estimated_api_cost_usd"], row["completion_percent"], s=70,
                           marker="o" if model == "astra" else "s", facecolors=COLORS[model] if model == "astra" else "none",
                           edgecolors=COLORS[model], linewidths=1.4, alpha=.86, zorder=4)
                dx = -7 if index % 2 else 7
                dy = 9 if index % 2 else -16
                ax.annotate(str(row["display_trial"]), (row["estimated_api_cost_usd"], row["completion_percent"]),
                            xytext=(dx, dy), textcoords="offset points", fontsize=8.5,
                            color=COLORS[model], ha="right" if dx < 0 else "left")
        ax.set_title("Task {} | {}".format(task, TASK_NAMES[task]), loc="left", fontsize=13, fontweight="semibold", pad=12)
        ax.set_xlabel("Estimated API cost per run (USD)")
        ax.set_xlim(0, 11.5)
        ax.set_ylim(0, 113)
        ax.set_yticks([0, 25, 50, 75, 100])
        ax.xaxis.set_major_formatter(FuncFormatter(lambda value, _: "${:g}".format(value)))
        axes_style(ax, "both")
    axes[0].set_ylabel("Final goal completion (%)")
    footer(fig, "Higher completion at lower cost appears toward the upper left; tasks are compared in separate panels.\nCosts are recorded public-rate estimates using actual cache usage. Task 4: retained run set.")
    save(fig, "04_cost_completion_scatter", "Cost versus completion", "Shows cost/performance trade-offs and whether expensive episodes also achieved their goals.")


def subtask_heatmap():
    goal_names = {0: ["Front butter", "Pudding", "Drawer closed"],
                  1: ["Soup", "Butter", "Tomato sauce"],
                  4: ["Back butter", "Pudding", "Drawer closed", "Bowl on cabinet"]}
    fig, axes = plt.subplots(1, 3, figsize=(15.6, 7.5), gridspec_kw={"width_ratios": [3, 3, 4]})
    fig.subplots_adjust(left=.075, right=.985, top=.79, bottom=.18, wspace=.29)
    title(fig, 5, "Which final conditions were satisfied?", "Ten episode rows per task; columns are native goal conditions")
    legend(fig, .903, [Patch(facecolor="#edf0f4", edgecolor="#b8bec7", label="Condition not met")])
    for ax, task in zip(axes, TASKS):
        labels = goal_names[task]
        pixels = np.ones((10, len(labels), 3))
        flags = np.zeros((10, len(labels)), dtype=bool)
        for model_index, model in enumerate(MODELS):
            for row_index, row in enumerate(cohort(task, model)):
                native = read_json(WORKSPACE / row["source_summary"])["trial_score"]
                goals = native["goals"]
                assert len(goals) == len(labels)
                position = model_index * 5 + row_index
                flags[position] = [goal["satisfied"] for goal in goals]
                color = np.array(matplotlib.colors.to_rgb(COLORS[model]))
                for column, satisfied in enumerate(flags[position]):
                    pixels[position, column] = color if satisfied else np.array([237, 240, 244]) / 255
                assert abs(flags[position].mean() * 100 - row["completion_percent"]) < 1e-7
        ax.imshow(pixels, aspect="auto", interpolation="nearest")
        for row in range(10):
            for column in range(len(labels)):
                ax.text(column, row, "✓" if flags[row, column] else "×", ha="center", va="center", fontsize=15,
                        color="white" if flags[row, column] and row < 5 else "#28313b")
        ax.set_xticks(range(len(labels)))
        ax.set_xticklabels(labels, fontsize=9, rotation=25, ha="right")
        ax.set_yticks(range(10))
        ax.set_yticklabels(["Astra {}".format(n) for n in range(1, 6)] + ["Opus {}".format(n) for n in range(1, 6)], fontsize=9)
        for index, label in enumerate(ax.get_yticklabels()):
            label.set_color(COLORS["astra" if index < 5 else "opus"])
        ax.set_xticks(np.arange(-.5, len(labels), 1), minor=True)
        ax.set_yticks(np.arange(-.5, 10, 1), minor=True)
        ax.grid(which="minor", color="white", linewidth=2)
        ax.axhline(4.5, color="#38424e", linewidth=1)
        ax.tick_params(which="both", length=0)
        for spine in ax.spines.values():
            spine.set_visible(False)
        ax.set_title("Task {} | {}".format(task, TASK_NAMES[task]), loc="left", fontsize=13, fontweight="semibold", pad=12)
    footer(fig, "Colored cells = final condition met; gray cells = not met. Final state is shown, not whether a condition was met temporarily.\nNative predicates score final placements/closure; they do not directly enforce every instruction's temporal order. Task 4: retained run set.")
    save(fig, "05_subtask_heatmap", "Subtask completion heatmap", "Best for explaining the partial Task 1 outcomes by object/condition rather than only a percentage.")


def formatted(value, sd=None, decimals=1):
    base = ("{:,." + str(decimals) + "f}").format(value)
    return base if sd is None else base + " ± " + ("{:,." + str(decimals) + "f}").format(sd)


def table_figure(number, heading, subtitle, columns, cells, widths, row_models, task_rows, figsize):
    fig, ax = plt.subplots(figsize=figsize)
    ax.axis("off")
    fig.subplots_adjust(left=.025, right=.975, top=.83, bottom=.10)
    title(fig, number, heading, subtitle)
    table = ax.table(cellText=cells, colLabels=columns, colWidths=widths, cellLoc="center", colLoc="center",
                     loc="center", bbox=[0, 0, 1, 1])
    table.auto_set_font_size(False)
    table.set_fontsize(10 if len(cells) > 10 else 11)
    for (row, column), cell in table.get_celld().items():
        cell.set_edgecolor("#dce1e8")
        cell.set_linewidth(.6)
        cell.PAD = .055
        if row == 0:
            cell.set_facecolor("#283647")
            cell.get_text().set_color("white")
            cell.get_text().set_weight("semibold")
        else:
            cell.set_facecolor("#f3f6fa" if task_rows[row - 1] % 2 == 0 else "white")
            if column == 1:
                cell.get_text().set_color(COLORS[row_models[row - 1]])
                cell.get_text().set_weight("semibold")
    return fig


def per_run_table(task=None):
    rows = sorted(RECORDS, key=lambda row:(row["task_id"], MODELS.index(row["model"]), row["display_trial"]))
    if task is not None:
        rows = [row for row in rows if row["task_id"] == task]
    columns = ["Task", "Model", "Run", "Goal\n(%)", "Stop", "Calls", "Action\nsteps", "Output\ntokens (k)", "API cost\n(USD)", "Wall time\n(min)"]
    cells, models, groups = [], [], []
    for row in rows:
        stop = {"success": "Success", "model_done": "Declared done", "give_up": "Give up"}.get(row["termination_reason"], row["termination_reason"])
        cells.append([row["task_id"], NAMES[row["model"]], row["display_trial"], formatted(row["completion_percent"]), stop,
                      row["api_calls"], "{:,}".format(row["action_steps"]), formatted(row["total_output_tokens"] / 1000),
                      "$" + formatted(row["estimated_api_cost_usd"], decimals=2), formatted(row["elapsed_seconds"] / 60)])
        models.append(row["model"])
        groups.append(TASKS.index(row["task_id"]))
    heading = "Every saved episode" if task is None else "Every episode | Task {}".format(task)
    fig = table_figure(6, heading, "One row per run; no averaging or variability hidden", columns, cells,
                       [.045, .065, .045, .075, .13, .06, .09, .13, .13, .13], models, groups,
                       (16.8, 13.6 if task is None else 6.8))
    footer(fig, "Output includes reasoning; wall time includes API requests. A declared-done stop is not full success unless all goals are met.\nTask 4 uses the current retained run set.", y=.035)
    name = "06_per_run_table" if task is None else "06_task{}_run_table".format(task)
    save(fig, name, "Per-run results table" if task is None else "Task {} per-run table".format(task),
         "Best for inspecting individual calls, steps, resource use and termination outcomes.", primary=task is None)


def summary_table():
    columns = ["Task", "Model", "Full\nsuccesses", "Goal completion\n(%)", "Output tokens\n(k/run)", "Estimated API cost\n(USD/run)", "Wall-clock time\n(min/run)"]
    cells, models, groups = [], [], []
    for group, task in enumerate(TASKS):
        for model in MODELS:
            rows = cohort(task, model)
            success = sum(row["full_success_percent"] == 100 for row in rows)
            cells.append([task, NAMES[model], "{}/5".format(success),
                          formatted(*stats(task, model, "completion_percent")),
                          formatted(*stats(task, model, "total_output_tokens", .001)),
                          formatted(*stats(task, model, "estimated_api_cost_usd"), decimals=2),
                          formatted(*stats(task, model, "elapsed_seconds", 1 / 60))])
            models.append(model)
            groups.append(group)
    fig = table_figure(7, "Compact results table", "Mean ± sample standard deviation across five saved episodes per model/task",
                       columns, cells, [.045, .08, .09, .18, .19, .21, .205], models, groups, (16, 5.4))
    footer(fig, "Output tokens include reasoning; costs are public-rate estimates; wall-clock includes API waiting.\nFull successes are counts, not mean ± SD. Task 4 uses the current retained run set; all episodes use state 0 and seed 0.", y=.028)
    save(fig, "07_summary_table", "Compact summary table", "Best single reference for the requested metrics, with full success counts and exact mean ± SD values.")


def gallery():
    primary = [item for item in FIGURES if item["primary"]]
    assert len(primary) == 7
    card_w, card_h, gap = 1000, 770, 28
    sheet = Image.new("RGB", (card_w * 2 + gap * 3, card_h * 4 + gap * 5 + 95), "#edf1f5")
    draw = ImageDraw.Draw(sheet)
    heading_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 30)
    label_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 23)
    draw.text((gap, 24), "Astra vs Opus | Choose a figure layout", fill="#1b2430", font=heading_font)
    for index, item in enumerate(primary):
        x = gap + index % 2 * (card_w + gap)
        y = 100 + gap + index // 2 * (card_h + gap)
        draw.rectangle((x, y, x + card_w, y + card_h), fill="white")
        draw.text((x + 20, y + 18), "{}  {}".format(index + 1, item["title"]), fill="#1b2430", font=label_font)
        image = Image.open(OUT / item["file"]).convert("RGB")
        image.thumbnail((card_w - 30, card_h - 75), Image.Resampling.LANCZOS if hasattr(Image, 'Resampling') else Image.LANCZOS)
        sheet.paste(image, (x + (card_w - image.width) // 2, y + 65 + (card_h - 75 - image.height) // 2))
    x, y = gap + (card_w + gap), 100 + gap + 3 * (card_h + gap)
    draw.rectangle((x, y, x + card_w, y + card_h), fill="white")
    draw.text((x + 36, y + 45), "Suggested choices", fill="#1b2430", font=heading_font)
    for index, text in enumerate(("1  Variability and outliers", "2  API waiting versus other time", "3  Sequential goal progress", "5  Which conditions failed", "7  Compact publication table")):
        draw.text((x + 36, y + 125 + index * 70), text, fill="#465160", font=label_font)
    sheet.save(OUT / "00_gallery.png")


def main():
    global RECORDS
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", choices=("wallclock",), help="Regenerate only the wall-clock figure and gallery")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "svg.fonttype": "none", "pdf.fonttype": 42})
    RECORDS, _, sources = gather()
    if args.only == "wallclock":
        manifest = read_json(OUT / "figure_sources.json")
        assert manifest["source_comparison_sha256"] == sources
        time_breakdown()
        updated = FIGURES[0]
        assert sum(item["file"] == updated["file"] for item in manifest["figures"]) == 1
        manifest["figures"] = [updated if item["file"] == updated["file"] else item for item in manifest["figures"]]
        manifest["time_figure_metric"] = "total_api_latency_seconds"
        manifest["time_figure_includes_other_elapsed_time"] = False
        manifest["note"] = "Figure options use the current saved cohorts. Output-token statistics include reported reasoning; the time figure uses measured API request time only."
        FIGURES[:] = manifest["figures"]
        gallery()
        (OUT / "figure_sources.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"outdir": str(OUT), "runs": len(RECORDS),
                          "updated": "02_wallclock_breakdown", "gallery": "00_gallery.png"}), flush=True)
        return
    individual_dots()
    time_breakdown()
    progress_curves()
    cost_completion()
    subtask_heatmap()
    per_run_table()
    for task in TASKS:
        per_run_table(task)
    summary_table()
    gallery()
    lines = ["# Figure options", "", "[Gallery preview](00_gallery.png)", "",
             "All figures use the current five saved runs per model on Tasks 0, 1 and 4: 30 episodes, max effort, state 0, seed 0. Task 4 uses its retained set. Blue is Astra and orange is Opus. Mean/variability summaries use sample SD (ddof=1).", "",
             "| Option | PNG | Best use |", "|---|---|---|"]
    for index, item in enumerate((item for item in FIGURES if item["primary"]), 1):
        lines.append("| {} | [{}]({}) | {} |".format(index, item["title"], item["file"], item["description"]))
    lines += ["", "The requested headline metrics are goal completion, output tokens (including reasoning), estimated API cost and measured episode wall-clock time. Individual dots and the summary table present all four. Other figures focus on the relationships or recorded conditions best suited to their layout.", "",
              "API request time includes network/provider waiting. The API time figure excludes other episode time, and its whiskers use the sample SD of API time across five runs. Goal-progress curves use observed decision-end scores against action steps, with no reconstructed wall-clock timing. Cost/completion points show exact recorded values. The heatmap shows final native conditions, including any conditions lost during a run.", "",
              "## Individual run tables", ""]
    for task in TASKS:
        lines.append("- [Task {} table](06_task{}_run_table.png)".format(task, task))
    lines += ["", "Each primary figure/table also has PDF and SVG exports with the same filename stem. [Source manifest](figure_sources.json).", "",
              "Rebuild with `wsl -d Ubuntu-24.04 --exec /root/projects/LIBERO-LOHO/.venv/bin/python scripts/create_figure_options.py` from the workspace.", ""]
    (OUT / "README.md").write_text("\n".join(lines), encoding="utf-8")
    manifest = {"source_comparison_sha256": sources, "runs": [{key:row[key] for key in ("task_id", "model", "display_trial", "run_id", "source_summary", "summary_sha256")} for row in RECORDS],
                "n_per_task_model": 5, "primary_options": 7, "figures": FIGURES,
                "time_figure_metric": "total_api_latency_seconds", "time_figure_includes_other_elapsed_time": False,
                "note": "Figure options use the current saved cohorts. Output-token statistics include reported reasoning; the time figure uses measured API request time only."}
    (OUT / "figure_sources.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps({"outdir": str(OUT), "runs": len(RECORDS), "primary_options": 7, "individual_exports": len(FIGURES), "gallery": "00_gallery.png"}), flush=True)


if __name__ == "__main__":
    main()
