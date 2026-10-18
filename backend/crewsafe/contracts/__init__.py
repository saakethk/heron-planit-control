"""Frozen contracts.

- `api`: JSON the iOS app reads and writes. Mirrors `frontend/ios/CrewSafe/Models/Models.swift`.
- `events`: messages services exchange on the bus (Kafka topics).

Change these deliberately: the app and every service depend on them.
"""
