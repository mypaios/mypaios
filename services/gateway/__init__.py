"""Gateways — talk to Pi from anywhere (OpenClaw-style remote channels).

v1: Telegram bot (official Bot API, long-polling — no inbound ports, no cloud
relay beyond Telegram itself). The user creates a bot with @BotFather and
pastes the token into Pi's settings; an allowlist of chat IDs gates who can
talk to it. Disabled by default.
"""
