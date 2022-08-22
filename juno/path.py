from os import path
from pathlib import Path
from typing import Any

from . import json, yaml


def home_path(*args: str) -> Path:
    path = Path(Path.home(), ".juno").joinpath(*args)
    path.mkdir(parents=True, exist_ok=True)
    return path


def full_path(root: str, rel_path: str) -> str:
    return path.join(path.dirname(root), *filter(None, rel_path.split("/")))


def load_json_file(path: str) -> Any:
    with open(path, mode="r", encoding="utf-8") as f:
        return json.load(f)


def save_json_file(obj: Any, path: str, indent: int | None = None) -> None:
    with open(path, mode="w", encoding="utf-8") as f:
        return json.dump(obj, f, indent=indent)


def load_yaml_file(path: str) -> Any:
    with open(path, mode="r", encoding="utf-8") as f:
        return yaml.load(f)


def save_yaml_file(obj: Any, path: str, indent: int | None = None) -> Any:
    with open(path, mode="w", encoding="utf-8") as f:
        return yaml.dump(obj, f, indent=indent)


def load_text_file(path: str) -> str:
    with open(path, mode="r", encoding="utf-8") as f:
        return f.read()


def save_text_file(obj: str, path: str) -> Any:
    with open(path, mode="w", encoding="utf-8") as f:
        return f.write(obj)
