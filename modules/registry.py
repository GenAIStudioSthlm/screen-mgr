"""ModuleRegistry — single source of truth for which modules exist in this
screen-mgr instance and which are enabled.

In-code modules register themselves at import time via `registry.register(...)`.
The enabled state lives in `data/modules.json` so it survives restarts.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from modules.base import Module


MODULES_FILE = Path("data/modules.json")


class ModuleRegistry:
    def __init__(self) -> None:
        self._modules: dict[str, "Module"] = {}
        self._enabled: dict[str, bool] = {}
        self._load()

    # --- registration ---------------------------------------------------

    def register(self, module: "Module") -> None:
        if not module.id:
            print(f"[modules] refusing to register module without id: {module!r}")
            return
        if module.id in self._modules:
            print(f"[modules] duplicate registration for '{module.id}'; keeping existing")
            return
        self._modules[module.id] = module
        # Default new modules to enabled. Persistence kicks in only when the
        # admin toggles it explicitly.
        self._enabled.setdefault(module.id, True)
        print(f"[modules] registered: {module.id} ({', '.join(module.type)})")

    # --- lookup ---------------------------------------------------------

    def get(self, module_id: str) -> "Module | None":
        return self._modules.get(module_id)

    def list(self) -> list["Module"]:
        return list(self._modules.values())

    # --- enabled state --------------------------------------------------

    def is_enabled(self, module_id: str) -> bool:
        return self._enabled.get(module_id, True)

    def enable(self, module_id: str) -> None:
        self._enabled[module_id] = True
        self._save()

    def disable(self, module_id: str) -> None:
        self._enabled[module_id] = False
        self._save()

    # --- persistence ----------------------------------------------------

    def _load(self) -> None:
        if not MODULES_FILE.exists():
            return
        try:
            with open(MODULES_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._enabled = data.get("enabled", {}) or {}
        except (OSError, json.JSONDecodeError) as e:
            print(f"[modules] failed to read {MODULES_FILE}: {e}")

    def _save(self) -> None:
        MODULES_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(MODULES_FILE, "w", encoding="utf-8") as f:
            json.dump({"enabled": self._enabled}, f, indent=2)


# Singleton instance imported by route handlers.
registry = ModuleRegistry()
