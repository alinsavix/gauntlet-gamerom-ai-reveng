"""Projectile hit outcome shared by collision, damage, and effect writers."""

from __future__ import annotations


CONSUMED = -1      # resolve_shot_hit: mob_unlink(shooter) + picture cleared
