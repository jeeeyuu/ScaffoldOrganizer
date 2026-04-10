import json

from nicegui import ui

from .config import load_config
from .db import connect, init_db, set_setting
from .ui import build_ui


def main() -> None:
    config = load_config()
    init_db(config.db_path)
    with connect(config.db_path) as conn:
        settings_map = {
            "openai_api_key": config.openai_api_key,
            "openai_base_url": config.openai_base_url,
            "prompt_id": config.prompt_id,
            "default_model": config.default_model,
            "model": config.default_model,
            "export_dir": config.export_dir,
            "export_filename_format": config.export_filename_format,
            "prompt_variables": json.dumps(config.prompt_variables, ensure_ascii=True),
            "runtime_overrides": config.runtime_overrides,
        }
        for key, value in settings_map.items():
            set_setting(conn, key, value)

    run_kwargs = dict(
        root=lambda: build_ui(config),
        title="ScaffoldOrganizer",
        reload=False,
        native=config.native,
    )
    if config.native:
        run_kwargs["window_size"] = (config.window_width, config.window_height)
        run_kwargs["frameless"] = config.frameless
    ui.run(**run_kwargs)


if __name__ in {"__main__", "__mp_main__"}:
    main()
