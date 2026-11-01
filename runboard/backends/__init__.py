"""Compute backends. Each one launches a run, reports its status, streams its log and brings its outputs home.

Adding a backend: subclass Backend in a new module and register it in BACKENDS.
"""
from .base import ACTIVE, DONE, Backend
from .kaggle import KaggleBackend
from .local import LocalBackend
from .remote import SlurmBackend, SSHBackend

BACKENDS: dict[str, Backend] = {b.name: b for b in (KaggleBackend(), LocalBackend(), SSHBackend(), SlurmBackend())}

__all__ = ["ACTIVE", "DONE", "Backend", "BACKENDS"]
