"""Domain models for the redesigned admin.

Existing models (`screens.py`, etc.) still live at the project root for
backward compatibility; new redesign-era models land here. Phase 8
cutover may relocate the legacy modules into this package too.
"""

from models.zones import Zone, ZoneManager, zone_manager  # noqa: F401
from models.scenes import Scene, SceneManager, scene_manager, ZoneOverride  # noqa: F401
