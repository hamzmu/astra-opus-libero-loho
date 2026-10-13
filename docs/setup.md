# Installation and running the benchmark

This guide installs the simulator and reproduces the Astra/Opus evaluation protocol. The study used **Windows 11 with WSL2, Ubuntu 24.04, Python 3.8.20 and headless OSMesa rendering**. Model responses vary between episodes, so rerunning the protocol can produce different results.

## What to install

- **Git** to clone this evaluator and the upstream simulator. Windows users can install [Git for Windows](https://git-scm.com/install/windows).
- **WSL2 with Ubuntu 24.04** for the validated Windows workflow.
- **Ubuntu rendering/build libraries**, installed below.
- **uv and Python 3.8**, installed by the included setup script. uv manages an isolated environment; see its [installation documentation](https://docs.astral.sh/uv/getting-started/installation/).
- **Python dependencies** from [requirements-sim.txt](../requirements/requirements-sim.txt), including the simulator, HTTP clients, plotting and video libraries.
- **FFmpeg and DejaVu fonts** for rebuilding comparison videos.
- **Provider API credentials and model access** for paid episodes. Simulator-only smoke tests need no credentials.

A GPU, policy training and demonstration dataset downloads are not required. The upstream simulator checkout supplies the task definitions, assets and stored initial states.

## 1. Clone this repository

In PowerShell, clone the repository:

```powershell
git clone -c core.autocrlf=false https://github.com/hamzmu/astra-opus-libero-loho.git
Set-Location astra-opus-libero-loho
```

If you already have the repository, start in its root directory. Keeping shell scripts with LF line endings avoids Bash errors when the clone is on a Windows drive.

## 2. Install WSL2 and Ubuntu

Skip installation if `Ubuntu-24.04` is already available. Otherwise, run in **PowerShell as Administrator**, restart if prompted, and complete Ubuntu's user setup. These commands follow [Microsoft's WSL installation guide](https://learn.microsoft.com/en-us/windows/wsl/install).

```powershell
wsl --install -d Ubuntu-24.04
wsl --list --verbose
```

The distribution should show version **2**. If it shows version 1:

```powershell
wsl --set-version Ubuntu-24.04 2
```

The PowerShell launcher currently selects the distribution named `Ubuntu-24.04` explicitly.

## 3. Install Linux libraries and the pinned simulator

From the repository root in PowerShell, enter Bash in that distribution:

```powershell
wsl -d Ubuntu-24.04 --exec bash
```

Run the following **inside Bash**, from the Linux path to this repository. For a Windows clone, that path is under `/mnt/c/...`; `pwd` should show the repository root containing `src/`, `requirements/` and `scripts/`.

```bash
sudo apt update
sudo apt install -y git curl build-essential \
    libosmesa6 libosmesa6-dev libgl1 libgl1-mesa-dri libegl1 \
    libglew-dev libglfw3 libglib2.0-0t64 ffmpeg fonts-dejavu-core

task_sim_repo="$HOME/projects/LIBERO-LOHO"
mkdir -p "$HOME/projects"
if [ ! -d "$task_sim_repo/.git" ]; then
    git clone https://github.com/markli1hoshipu/LIBERO-LOHO.git "$task_sim_repo"
fi
git -C "$task_sim_repo" fetch origin 600709f7c5f19a370c477216f51c8d6b163c6164
git -C "$task_sim_repo" checkout --detach 600709f7c5f19a370c477216f51c8d6b163c6164

bash scripts/setup_wsl.sh

"$task_sim_repo/.venv/bin/python" --version
git -C "$task_sim_repo" rev-parse HEAD
```

Pin the revision **before** running the installer: [setup_wsl.sh](../scripts/setup_wsl.sh) otherwise clones the latest upstream default branch. It installs uv if needed, creates `$HOME/projects/LIBERO-LOHO/.venv`, installs the pinned requirements and editable simulator package, checks dependency consistency, and writes resolved package versions to `setup_logs/wsl-freeze.txt`.

The main runtime versions used in the study are:

| Component | Version |
|---|---|
| Python | 3.8.20 |
| robosuite | 1.4.0 |
| MuJoCo | 2.3.7 |
| NumPy | 1.22.4 |
| Gym | 0.25.2 |
| PyTorch | 1.11.0+cpu |
| OpenCV | 4.6.0.66 |

Use the same WSL user for installation and execution: the launcher finds the environment in that user's home directory. The original study used `/root/projects/LIBERO-LOHO`; normal-user installations use the corresponding `/home/<user>/projects/LIBERO-LOHO` path. The simulator and virtual environment stay on the Linux filesystem even when this evaluator is cloned on a Windows drive.

Exit Bash to return to PowerShell:

```bash
exit
```

## 4. Configure credentials

In PowerShell, create `.env` only if one does not already exist, then edit it:

```powershell
if (-not (Test-Path -LiteralPath '.env')) {
    Copy-Item -LiteralPath '.env.example' -Destination '.env'
}
notepad .env
```

Fill in the key for each provider you will run:

```dotenv
OPENAI_API_KEY=your_openai_api_key
ANTHROPIC_API_KEY=your_anthropic_api_key
```

Astra uses `OPENAI_API_KEY`; Opus uses `ANTHROPIC_API_KEY`. Account access must cover the model IDs configured in [comparison-models.json](../config/comparison-models.json): `gpt-6-astra` and `claude-opus-5-5`.

Credentials are read from the runner's process environment first, then the repository-root `.env`. This file supplies credentials only; renderer settings and other options are configured by the launcher or command-line flags. The existing `.gitignore` excludes `.env` and permits the blank [.env.example](../.env.example).

## 5. Run an episode

From the repository root in PowerShell, use the WSL environment installed above. Credentials are read from the environment or local `.env`: `OPENAI_API_KEY` for Astra and `ANTHROPIC_API_KEY` for Opus.

```powershell
# Simulator-only check; no model requests
.\scripts\run-loho.ps1 -Platform wsl smoke --task 0 --states 1

# Optional: smoke-test all five tasks and five stored states per task
.\scripts\run-loho.ps1 -Platform wsl smoke --states 5

# One fresh episode with the comparison defaults
.\scripts\run-loho.ps1 -Platform wsl control --model astra --task 0 --initial-state 0 --seed 0
.\scripts\run-loho.ps1 -Platform wsl control --model opus --task 0 --initial-state 0 --seed 0
```

Change `--task` to select task IDs **0–4**. Episodes stop on simulator success, model-declared `done`/`give_up`, call/step limits or errors; a model's `done` claim does not establish success. Astra's configured `xhigh` fallback applies only if the API explicitly rejects `max` effort. Ordinary API failures stop the episode without automatic retries; three consecutive rejected motion tools also terminate it.

For Linux or a WSL Bash session, run the same commands through the shell launcher:

```bash
bash scripts/run_wsl.sh smoke --task 0 --states 1
bash scripts/run_wsl.sh control --model astra --task 0 --initial-state 0 --seed 0
bash scripts/run_wsl.sh control --model opus --task 0 --initial-state 0 --seed 0
```

The shell launcher sets `MUJOCO_GL=osmesa` and `PYOPENGL_PLATFORM=osmesa` by default. Neither a desktop display nor a model policy checkpoint is needed.

## Evaluation defaults

| Setting | Comparison protocol |
|---|---|
| Models/effort | GPT-6 Astra max; Claude Opus 5.5 max |
| Initial state and seed | Stored state 0; seed 0; fresh conversation per episode |
| Inputs | Static + wrist, 224 × 224 RGB each, plus measured robot proprioception |
| Actions | Absolute pose motion tools, 10 Hz, 25% speed limit |
| History | Full conversation, images and tool results within the episode |
| Limits | 80 API requests; 2,000 action steps; 128,000 output tokens per request |
| Spending cap | None; estimated cost is recorded |
| Score | Final native simulator goal predicates; all conditions required for full success |

The five initial settling steps precede the action budget. See the [shared prompt example](../prompts/pose-tools-v1_task0_max.txt) and [motion-tool schema](../prompts/pose-tools-v1_tools.json). Prompts and workspace facts are generated for each actual task at runtime; each recorded study episode retains its exact prompt.

## Repeat five episodes per model on Tasks 0, 1 and 4

After the smoke test succeeds and credentials are configured, this **Bash** loop runs 30 paid episodes sequentially with the same state, seed and default settings. It creates a new batch directory and stops if the runner exits with an error; unsuccessful completed episodes remain part of the saved batch.

```bash
task_batch="reproduction_$(date +%Y%m%d_%H%M%S)"
for task_id in 0 1 4; do
    for model in astra opus; do
        for trial in 1 2 3 4 5; do
            bash scripts/run_wsl.sh control \
                --model "$model" --task "$task_id" --initial-state 0 --seed 0 \
                --outdir "loho_runs/$task_batch/task_$task_id/${model}_trial_$trial" || exit 1
        done
    done
done

"$HOME/projects/LIBERO-LOHO/.venv/bin/python" scripts/summarize_runs.py \
    --root "loho_runs/$task_batch" --output "loho_runs/$task_batch/task_metrics.json"
```

Use a new batch directory for another comparison. The Bash launcher and this loop work with the installing user's home directory. The separate historical automation helpers `prepare_task_reference.py` and `run_study_comparison.py` currently assume `/root/projects/LIBERO-LOHO`; they require the original root-user runtime.

## Saved results and rebuilding figures

Single episodes default to `loho_runs/<platform>_control_<profile>_<timestamp>/`. Use `--outdir` to choose a directory; Windows paths passed to the WSL runner must be translated to Linux paths such as `/mnt/c/...`.

Control episodes save `summary.json`, `api_attempts.jsonl`, `conversation.json`, the static `episode.mp4` and wrist `wrist_episode.mp4`. Summaries contain the exact prompt, actions, measured feedback, goal scores, request usage, estimated cost and latency. Standalone observation PNGs are not saved for control episodes.

Cost accounting includes reported usage from failed, incomplete or invalid responses. Unknown usage remains unresolved rather than being treated as free. [Pricing snapshots](../config/pricing-astra.json) and [Opus pricing](../config/pricing-opus.json) supply the recorded estimates; provider billing determines actual charges.

Published figures summarize the current five saved episodes per model/task. Plot rebuilds require the corresponding `loho-study/task 0`, `task 1` and `task 4` run folders and their `latest_task*_comparison.json` pointers. The saved episode directories, dependency freeze files and original task references are included by the repository's Git ignore rules; credentials and regenerated environments remain excluded. The reproduction loop above generates a separate aggregate JSON; it does not replace the published study pointers.

With the published study inputs available, run these offline tools inside Bash:

```bash
task_python="$HOME/projects/LIBERO-LOHO/.venv/bin/python"
"$task_python" scripts/plot_study_comparison.py
"$task_python" scripts/create_figure_options.py
"$task_python" scripts/create_task_comparison_videos.py
"$task_python" scripts/create_static_task_grid.py
```

The last command uses the source manifests produced by the per-task video command. The combined video shows static cameras only and omits API waiting; both cameras were supplied during evaluation.

## Native Windows alternative

The included Windows installer creates `.venv-windows`, applies two local robosuite binding fixes, omits robomimic's Linux-only build dependency, and creates the short `C:\loho-libero` junction for long Task 4 filenames. WSL is the study's validated runtime; native Python is currently blocked by Windows Application Control on the study machine.

On a machine that permits native Python, install Git and Windows uv first. The uv command below is documented in the [official uv installation guide](https://docs.astral.sh/uv/getting-started/installation/#winget). Reopen PowerShell after installation if `uv` is not yet on `PATH`.

```powershell
winget install --id=astral-sh.uv -e
uv python install 3.8.20

if (-not (Test-Path -LiteralPath 'LIBERO-LOHO/.git')) {
    git clone https://github.com/markli1hoshipu/LIBERO-LOHO.git LIBERO-LOHO
}
git -C LIBERO-LOHO fetch origin 600709f7c5f19a370c477216f51c8d6b163c6164
git -C LIBERO-LOHO checkout --detach 600709f7c5f19a370c477216f51c8d6b163c6164

.\scripts\install_windows_dependencies.ps1
.\scripts\run-loho.ps1 -Platform windows smoke --task 0 --states 1
.\scripts\run-loho.ps1 -Platform windows control --model astra --task 0 --initial-state 0 --seed 0
```

## Troubleshooting

| Symptom | Check |
|---|---|
| `Ubuntu-24.04` not found | Run `wsl --list --verbose`; install that distribution or adapt the launcher's distribution name. |
| Python environment not found | Use the same WSL user as installation and verify `$HOME/projects/LIBERO-LOHO/.venv/bin/python` exists. |
| OSMesa/OpenGL import failure | Install the Linux libraries in step 3 and use `MUJOCO_GL=osmesa`, `PYOPENGL_PLATFORM=osmesa` in Bash. |
| Bash reports `$'\r'` or invalid shell options | Ensure `scripts/*.sh` have LF line endings. |
| Missing/incompatible Python packages | Rerun `bash scripts/install_wsl_dependencies.sh`; preserve the versions in `requirements/requirements-sim.txt`. |
| Missing key or API access error | Check the selected provider's `.env` entry, model access and quota; inspect the saved request ledger. |
| Native Windows Python is blocked | Use WSL. Changing PowerShell execution policy does not resolve Windows Application Control restrictions. |
