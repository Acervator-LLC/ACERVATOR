"""Ambient animation particle for the bot node widget.

Position, velocity and remaining life in widget coordinates. Carries no
Qt dependency, so it is defined unconditionally.
"""

from __future__ import annotations


# -------------------------------------------------------------------
# Particle system for ambient animation
# -------------------------------------------------------------------
class Particle:
    def __init__(self, x, y, vx, vy, life, size):
        self.x, self.y = x, y
        self.vx, self.vy = vx, vy
        self.life = life
        self.max_life = life
        self.size = size

    def update(self, dt):
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.life -= dt

    @property
    def alpha(self):
        return max(0, self.life / self.max_life)
