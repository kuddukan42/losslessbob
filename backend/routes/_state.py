"""Module-level state shared between backend/app.py and its Blueprints (TODO-369).

Lives here instead of in a ``create_app()`` closure so a route moved into a Blueprint
module reads the same object as the routes still in app.py.
"""

import time

# Set by create_app(); read by /api/system/uptime and /api/admin/status (TODO-285).
process_start_time: float = time.monotonic()
