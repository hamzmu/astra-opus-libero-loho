"""Explicit camera selection and synchronized RGB snapshots for the policy."""
CAMERA_CONFIGS = {
    "agentview": ("agentview",),
    "wrist": ("robot0_eye_in_hand",),
    "agentview-wrist": ("agentview", "robot0_eye_in_hand"),
}
CAMERA_LABELS = {
    "agentview": "Camera: agentview - fixed overview; same simulation observation.",
    "robot0_eye_in_hand": "Camera: robot0_eye_in_hand - moving Panda wrist view; same simulation observation.",
}


def camera_configuration(args):
    # Internal diagnostic callers and historical traces predate the CLI default.
    value = getattr(args, "cameras", None) or "agentview"
    if value not in CAMERA_CONFIGS:
        raise ValueError("Unsupported camera configuration: " + str(value))
    if getattr(args, "prompt_profile", "calibrated-v2") == "legacy-v1" and value != "agentview":
        raise ValueError("legacy-v1 requires the original agentview-only camera condition")
    return value


def camera_names(args):
    return list(CAMERA_CONFIGS[camera_configuration(args)])


def camera_orientations(args):
    names = camera_names(args)
    return {name: getattr(args, "orientation", "rotate180") if name == "agentview"
            else getattr(args, "wrist_orientation", "flip_vertical") for name in names}


def validate_camera_frame(rgb, resolution, camera):
    import numpy as np
    value = np.asarray(rgb)
    if value.shape != (resolution, resolution, 3) or value.dtype != np.uint8:
        raise ValueError("Invalid RGB shape or dtype for camera " + camera)
    return np.ascontiguousarray(value)


def camera_frames(obs, args):
    import numpy as np
    frames = {}
    for name, orientation in camera_orientations(args).items():
        key = name + "_image"
        if key not in obs:
            raise ValueError("Required camera observation is missing: " + key)
        rgb = validate_camera_frame(obs[key], args.resolution, name)
        if orientation == "rotate180":
            rgb = rgb[::-1, ::-1]
        elif orientation == "flip_vertical":
            rgb = rgb[::-1]
        elif orientation != "raw":
            raise ValueError("Unsupported image orientation: " + str(orientation))
        frames[name] = np.ascontiguousarray(rgb)
    return frames
