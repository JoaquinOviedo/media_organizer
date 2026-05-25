import json
import os
from pathlib import Path

class Config:
    def __init__(self, config_path: str = "config.json"):
        self.config_path = config_path
        self.settings = self._load_config()

    def _load_config(self) -> dict:
        if not os.path.exists(self.config_path):
            raise FileNotFoundError(f"Config file not found at: {self.config_path}")
        
        with open(self.config_path, "r", encoding="utf-8") as f:
            settings = json.load(f)
        
        # Ensure paths are absolute or relative to the working directory
        base_dir = Path.cwd()
        paths = settings.get("paths", {})
        for k, v in paths.items():
            paths[k] = str(Path(v).absolute())
        settings["paths"] = paths
        
        return settings

    @property
    def paths(self):
        return self.settings.get("paths", {})
        
    @property
    def processing(self):
        return self.settings.get("processing", {})

    @property
    def thresholds(self):
        return self.settings.get("thresholds", {})
        
    @property
    def scoring_weights(self):
        return self.settings.get("scoring_weights", {})
