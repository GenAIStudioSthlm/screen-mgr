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
        # Entries: [{"id": "robot-panel", "manifest_url": "http://..."}]
        self._external: list[dict] = []
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

    def unregister(self, module_id: str) -> None:
        self._modules.pop(module_id, None)

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

    # --- external modules ----------------------------------------------

    def external_entries(self) -> list[dict]:
        """Read-only view of the configured external manifest entries."""
        return list(self._external)

    def load_external(self) -> list[dict]:
        """Fetch every configured external manifest and register the
        resulting module. Returns a per-entry result list with `ok`,
        `id`, `manifest_url`, and on failure `error`. Errors don't raise
        — failed entries stay in config and can retry later."""
        # Local import to avoid a circular import at module-load time.
        from modules.external import fetch_manifest, build_external_module

        results: list[dict] = []
        for entry in self._external:
            url = entry.get("manifest_url", "")
            try:
                manifest = fetch_manifest(url)
                module = build_external_module(url, manifest)
                # If a fresh fetch yields a different id from the cached
                # entry, update the cached id so admin shows the truth.
                entry["id"] = module.id
                # Drop any stale instance and register the new one.
                self.unregister(module.id)
                self.register(module)
                results.append({"ok": True, "id": module.id, "manifest_url": url})
            except Exception as e:
                print(f"[modules] external manifest load failed ({url}): {e}")
                results.append(
                    {
                        "ok": False,
                        "id": entry.get("id", ""),
                        "manifest_url": url,
                        "error": str(e),
                    }
                )
        return results

    def add_external(self, manifest_url: str) -> dict:
        """Fetch a manifest, register the module, and persist the entry."""
        from modules.external import fetch_manifest, build_external_module

        manifest = fetch_manifest(manifest_url)
        module = build_external_module(manifest_url, manifest)
        # Replace any existing entry with the same id.
        self._external = [
            e for e in self._external if e.get("id") != module.id
        ]
        self._external.append({"id": module.id, "manifest_url": manifest_url})
        self.unregister(module.id)
        self.register(module)
        self._save()
        return {"id": module.id, "manifest_url": manifest_url}

    def remove_external(self, module_id: str) -> bool:
        """Drop the external entry and unregister the module. Returns True
        if anything was removed."""
        before = len(self._external)
        self._external = [
            e for e in self._external if e.get("id") != module_id
        ]
        removed_cfg = len(self._external) < before
        removed_mod = module_id in self._modules
        self.unregister(module_id)
        if removed_cfg or removed_mod:
            self._save()
        return removed_cfg or removed_mod

    # --- persistence ----------------------------------------------------

    def _load(self) -> None:
        if not MODULES_FILE.exists():
            return
        try:
            with open(MODULES_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._enabled = data.get("enabled", {}) or {}
            self._external = data.get("external", []) or []
        except (OSError, json.JSONDecodeError) as e:
            print(f"[modules] failed to read {MODULES_FILE}: {e}")

    def _save(self) -> None:
        MODULES_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(MODULES_FILE, "w", encoding="utf-8") as f:
            json.dump(
                {"enabled": self._enabled, "external": self._external},
                f,
                indent=2,
            )


# Singleton instance imported by route handlers.
registry = ModuleRegistry()
