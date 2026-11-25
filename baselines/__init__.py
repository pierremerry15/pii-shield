"""Frozen copies of the PathReview scrubber, used as evaluation baselines.

Both files reproduce ``safety/pii_scrubber.py`` from the CodePath PathReview repo
(MIT licensed, per its pyproject.toml) with one change: the ``structlog`` call is
removed so the baselines have no dependencies. The regexes and the scrub/detect logic
are byte-for-byte the originals. Do not "fix" them; they exist to be measured against.
"""
