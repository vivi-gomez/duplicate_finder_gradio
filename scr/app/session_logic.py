import json
from typing import Any, Dict, List

SESSION_FILE = "last_session.json"

def save_session(groups: List[Dict[str, Any]]):
    with open(SESSION_FILE, "w") as f:
        json.dump(groups, f, indent=2)

def load_last_session() -> List[Dict[str, Any]]:
    try:
        with open(SESSION_FILE, "r") as f:
            groups = json.load(f)
    except FileNotFoundError:
        groups = []
    # Al cargar, solo selecciona "OTROS"
    for group in groups:
        for file in group["files"]:
            file["seleccionado"] = (file["categoria"] == "OTROS")
        group["seleccionado"] = all(file["seleccionado"] for file in group["files"])
    return groups