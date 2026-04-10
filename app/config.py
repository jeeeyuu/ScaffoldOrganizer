import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass
class AppConfig:
    openai_api_key: str
    openai_base_url: str
    db_path: str
    export_dir: str
    export_filename_format: str
    prompt_id: str
    prompt_variables: dict
    default_model: str
    runtime_overrides: str
    window_width: int = 600
    window_height: int = 400
    native: bool = True
    frameless: bool = False


APP_NAME = "ScaffoldOrganizer"
REPO_CONFIG_PATH = Path(__file__).resolve().parents[1] / "config.json"
CONFIG_EXAMPLE_PATH = Path(__file__).resolve().parents[1] / "config_example.json"


def _user_config_dir() -> Path:
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME
    if os.name == "nt":
        return Path(os.getenv("APPDATA", Path.home() / "AppData" / "Roaming")) / APP_NAME
    return Path(os.getenv("XDG_CONFIG_HOME", Path.home() / ".config")) / APP_NAME


def _default_config_path() -> Path:
    if getattr(sys, "frozen", False):
        return _user_config_dir() / "config.json"
    return REPO_CONFIG_PATH


def _default_config_data() -> dict:
    return {
        "openai_api_key": "",
        "openai_base_url": "https://api.openai.com/v1",
        "db_path": "./data/app.db",
        "export_dir": "./exports",
        "export_filename_format": "todo_%Y-%m-%d_%H%M.md",
        "prompt_id": "",
        "prompt_variables": {},
        "default_model": "gpt-4.1",
        "runtime_overrides": "",
        "window_width": 600,
        "window_height": 400,
        "native": True,
        "frameless": False,
    }


def _resolve_path(value: str, base_dir: Path) -> str:
    path = Path(value)
    if path.is_absolute():
        return str(path)
    return str((base_dir / path).resolve())


def load_config(config_path: Path | None = None) -> AppConfig:
    path = config_path or _default_config_path()
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        if CONFIG_EXAMPLE_PATH.exists():
            seed = json.loads(CONFIG_EXAMPLE_PATH.read_text(encoding="utf-8"))
        else:
            seed = _default_config_data()
        path.write_text(json.dumps(seed, ensure_ascii=True, indent=2), encoding="utf-8")
        raw = seed
    else:
        raw = json.loads(path.read_text(encoding="utf-8"))
    base_dir = path.parent
    return AppConfig(
        openai_api_key=raw.get("openai_api_key", ""),
        openai_base_url=raw.get("openai_base_url", "https://api.openai.com/v1"),
        db_path=_resolve_path(raw.get("db_path", "./data/app.db"), base_dir),
        export_dir=_resolve_path(raw.get("export_dir", "./exports"), base_dir),
        export_filename_format=raw.get("export_filename_format", "todo_%Y-%m-%d_%H%M.md"),
        prompt_id=raw.get("prompt_id", ""),
        prompt_variables=raw.get("prompt_variables", {}),
        default_model=raw.get("default_model", "gpt-4.1"),
        runtime_overrides=raw.get("runtime_overrides", ""),
        window_width=int(raw.get("window_width", 600)),
        window_height=int(raw.get("window_height", 400)),
        native=bool(raw.get("native", True)),
        frameless=bool(raw.get("frameless", False)),
    )


def save_config(config: AppConfig, config_path: Path | None = None) -> None:
    path = config_path or _default_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "openai_api_key": config.openai_api_key,
        "openai_base_url": config.openai_base_url,
        "db_path": config.db_path,
        "export_dir": config.export_dir,
        "export_filename_format": config.export_filename_format,
        "prompt_id": config.prompt_id,
        "prompt_variables": config.prompt_variables,
        "default_model": config.default_model,
        "runtime_overrides": config.runtime_overrides,
        "window_width": config.window_width,
        "window_height": config.window_height,
        "native": config.native,
        "frameless": config.frameless,
    }
    path.write_text(json.dumps(data, ensure_ascii=True, indent=2), encoding="utf-8")
