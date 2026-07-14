"""Telegram Engine Service.

This is the *only* process that owns Telethon sessions and aiogram bots. The API
and Celery workers never open a Telegram client directly — they enqueue jobs that
this service executes. In Phase 0 it is a heartbeat placeholder.
"""
