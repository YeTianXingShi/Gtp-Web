from __future__ import annotations

from flask import Flask
from openai import OpenAI

from gtpweb.blueprints import register_blueprints
from gtpweb.config import AppConfig


def register_routes(app: Flask, config: AppConfig, _openai_client: OpenAI | None = None) -> None:
    """Backward-compatible wrapper around blueprint registration."""
    register_blueprints(app, config)
