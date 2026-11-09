"""Local user profiles under ~/.7beingbci/."""

from __future__ import annotations

import json
import re
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path

ROOT = Path.home() / ".7beingbci"
PROFILES = ROOT / "profiles"
SESSIONS = ROOT / "sessions"

# Emotiv-style mental commands (+ Neutral). Profiles may pick a subset.
ACTIONS = ("Neutral", "Push", "Pull", "Lift", "Drop", "Left", "Right")
MAX_ACTIONS = 7  # Neutral + up to 6 motion commands

# Profile ids are directory names under PROFILES — reject path traversal.
_PROFILE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")

DEFAULT_KEYMAP = {
    "Neutral": "",
    "Push": "w",
    "Pull": "s",
    "Lift": " ",
    "Drop": "shift",
    "Left": "a",
    "Right": "d",
    "Blink": "b",
    "Wink L": "q",
    "Wink R": "e",
    "Look L": "a",
    "Look R": "d",
}


@dataclass
class Profile:
    id: str
    name: str
    actions: list[str] = field(default_factory=lambda: ["Neutral", "Push", "Left"])
    keymap: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_KEYMAP))
    mental_threshold: float = 0.55
    debounce_ms: int = 400
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    has_calibration: bool = False
    has_model: bool = False
    last_cv_accuracy: float | None = None

    def dir(self) -> Path:
        return profile_dir(self.id)

    def meta_path(self) -> Path:
        return self.dir() / "profile.json"

    def calib_path(self) -> Path:
        return self.dir() / "calibration.npz"

    def model_path(self) -> Path:
        return self.dir() / "mental.joblib"


def ensure_dirs() -> None:
    PROFILES.mkdir(parents=True, exist_ok=True)
    SESSIONS.mkdir(parents=True, exist_ok=True)


def safe_profile_id(profile_id: str) -> str:
    """Return a jail-safe profile id or raise ValueError."""
    pid = (profile_id or "").strip()
    if not _PROFILE_ID_RE.fullmatch(pid):
        raise ValueError("invalid profile id")
    if pid in {".", ".."} or "/" in pid or "\\" in pid:
        raise ValueError("invalid profile id")
    return pid


def profile_dir(profile_id: str) -> Path:
    """Resolved directory for a profile, always under PROFILES."""
    ensure_dirs()
    pid = safe_profile_id(profile_id)
    root = PROFILES.resolve()
    path = (PROFILES / pid).resolve()
    if path.parent != root:
        raise ValueError("profile path escape")
    return path


def _slug(name: str) -> str:
    clean = re.sub(r"[^a-zA-Z0-9_-]+", "-", name.strip())[:32].strip("-") or "user"
    return f"{clean}-{uuid.uuid4().hex[:8]}"


def list_profiles() -> list[Profile]:
    ensure_dirs()
    found: list[Profile] = []
    for path in sorted(PROFILES.glob("*/profile.json")):
        try:
            found.append(load_profile(path.parent.name))
        except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError):
            continue
    return found


def load_profile(profile_id: str) -> Profile:
    folder = profile_dir(profile_id)
    path = folder / "profile.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    stored_id = safe_profile_id(str(raw.get("id") or profile_id))
    if stored_id != safe_profile_id(profile_id):
        raise ValueError("profile id mismatch")
    keymap = dict(DEFAULT_KEYMAP)
    keymap.update(raw.get("keymap") or {})
    actions = [a for a in raw.get("actions") or ["Neutral", "Push"] if a in ACTIONS]
    if "Neutral" not in actions:
        actions = ["Neutral", *actions]
    if len(actions) < 2:
        actions = ["Neutral", "Push"]
    actions = actions[:MAX_ACTIONS]
    profile = Profile(
        id=stored_id,
        name=raw.get("name") or profile_id,
        actions=actions,
        keymap=keymap,
        mental_threshold=float(raw.get("mental_threshold", 0.55)),
        debounce_ms=int(raw.get("debounce_ms", 400)),
        created_at=float(raw.get("created_at", time.time())),
        updated_at=float(raw.get("updated_at", time.time())),
        has_calibration=bool(raw.get("has_calibration")),
        has_model=bool(raw.get("has_model")),
        last_cv_accuracy=raw.get("last_cv_accuracy"),
    )
    if not profile.calib_path().exists():
        profile.has_calibration = False
    if not profile.model_path().exists():
        profile.has_model = False
    return profile


def save_profile(profile: Profile) -> Profile:
    ensure_dirs()
    profile.id = safe_profile_id(profile.id)
    profile.updated_at = time.time()
    profile.dir().mkdir(parents=True, exist_ok=True)
    profile.has_calibration = profile.calib_path().exists()
    profile.has_model = profile.model_path().exists()
    profile.meta_path().write_text(
        json.dumps(asdict(profile), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return profile


def create_profile(name: str, actions: list[str] | None = None) -> Profile:
    ensure_dirs()
    chosen = actions or ["Neutral", "Push", "Pull", "Left", "Right"]
    cleaned = [a for a in chosen if a in ACTIONS]
    if "Neutral" not in cleaned:
        cleaned = ["Neutral", *cleaned]
    cleaned = cleaned[:MAX_ACTIONS]
    if len(cleaned) < 2:
        cleaned = ["Neutral", "Push"]
    profile = Profile(id=_slug(name), name=name.strip() or "User", actions=cleaned)
    return save_profile(profile)


def delete_profile(profile_id: str) -> bool:
    path = profile_dir(profile_id)
    if not path.exists():
        return False
    for child in path.glob("*"):
        if child.is_file():
            child.unlink(missing_ok=True)
    path.rmdir()
    return True


def active_path() -> Path:
    ensure_dirs()
    return ROOT / "active_profile.txt"


def get_active_id() -> str | None:
    path = active_path()
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8").strip()
    return text or None


def set_active_id(profile_id: str | None) -> None:
    ensure_dirs()
    path = active_path()
    if not profile_id:
        path.unlink(missing_ok=True)
        return
    path.write_text(safe_profile_id(profile_id), encoding="utf-8")


def get_active_profile() -> Profile | None:
    pid = get_active_id()
    if not pid:
        return None
    try:
        return load_profile(pid)
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError):
        return None


def to_public(profile: Profile) -> dict:
    return {
        "id": profile.id,
        "name": profile.name,
        "actions": list(profile.actions),
        "keymap": dict(profile.keymap),
        "mental_threshold": profile.mental_threshold,
        "debounce_ms": profile.debounce_ms,
        "has_calibration": profile.has_calibration,
        "has_model": profile.has_model,
        "last_cv_accuracy": profile.last_cv_accuracy,
    }
