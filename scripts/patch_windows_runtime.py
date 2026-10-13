"""Repair two Robosuite 1.4.0 Windows binding assumptions, locally."""
import importlib.util
import os
from pathlib import Path

if os.name != "nt":
    raise SystemExit("This compatibility patch is Windows-only")

spec = importlib.util.find_spec("robosuite")
target = Path(spec.origin).parent / "utils" / "binding_utils.py"
source = target.read_text(encoding="utf-8")
replacements = {
    'ctypes.WinDLL(os.path.join(os.path.dirname(__file__), "mujoco.dll"))':
        'ctypes.WinDLL(os.path.join(os.path.dirname(mujoco.__file__), "mujoco.dll"))',
    'if macros.MUJOCO_GPU_RENDERING and os.environ.get("MUJOCO_GL", None) not in ["osmesa", "glx"]:':
        'if _SYSTEM != "Windows" and macros.MUJOCO_GPU_RENDERING and os.environ.get("MUJOCO_GL", None) not in ["osmesa", "glx"]:',
}
original = source
for old, new in replacements.items():
    if old in source:
        source = source.replace(old, new, 1)
    elif new not in source:
        raise SystemExit("Unexpected Robosuite source; refusing an unrecognized patch")
if source != original:
    backup = target.with_suffix(".py.upstream")
    if not backup.exists():
        backup.write_text(original, encoding="utf-8")
    target.write_text(source, encoding="utf-8")
print("Windows Robosuite binding: correct MuJoCo DLL location and GLFW rendering")

