import threading

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

state = AppState()
