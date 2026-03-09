from __future__ import annotations

from flask import Flask
from openai import OpenAI

from gtpweb.blueprints import register_blueprints
from gtpweb.config import AppConfig


def register_routes(app: Flask, config: AppConfig, openai_client: OpenAI) -> None:
    """Backward-compatible wrapper around blueprint registration."""
    register_blueprints(app, config, openai_client)
