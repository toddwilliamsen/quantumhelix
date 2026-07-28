import os
import threading
from collections import deque


class AppState:
    def __init__(self):
        self.streaming = False
        self.processed = 0
        self.seed = 301
        self.disagreements = 0
        self.active_clients = 0
        self.threshold = 0.68
        self.delay = 0.65
        self.batch = 5
        self.pipe = None
        self.ensemble = None
        self.alerter = None
        self.servicenow = None
        self.lock = threading.Lock()
        self.history_cache = []
        # Tenant used by the synthetic event generator (override with SIM_TENANT_ID).
        self.sim_tenant_id = int(os.environ.get("SIM_TENANT_ID", "1"))
        # Injected attack events consumed by the generator loop (thread-safe via lock).
        self.replay_queue = deque()
        self.playground = {
            "pca_dimensions": 4,
            "kernel_type": "simulator",
            "ensemble_weights": {"classical": 0.55, "quantum": 0.45},
            "latency_profile": "balanced",
        }
        self._bg_started = False
        self._generator_lock_fh = None


state = AppState()
