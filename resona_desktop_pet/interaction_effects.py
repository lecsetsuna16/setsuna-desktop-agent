"""Pure animation math for character-only physical-interaction feedback.

Keeping the easing calculations independent from Qt makes them deterministic and
cheap to test without starting the desktop application.
"""

from dataclasses import dataclass
import math


INTERACTION_DURATIONS_MS = {
    "head_pat": 1600,
    "cheek_poke": 1400,
    "hug": 2300,
    "shoulder_pat": 1600,
}

@dataclass(frozen=True)
class InteractionFrame:
    offset_x: float = 0.0
    offset_y: float = 0.0
    scale: float = 1.0
    scale_x: float = 1.0
    scale_y: float = 1.0
    rotation: float = 0.0


def sample_interaction(interaction: str, progress: float) -> InteractionFrame:
    """Return a smooth frame for *progress* in the closed interval [0, 1]."""
    if interaction not in INTERACTION_DURATIONS_MS:
        return InteractionFrame()

    progress = max(0.0, min(1.0, float(progress)))
    if progress <= 0.0 or progress >= 1.0:
        return InteractionFrame()

    def contact_envelope(start: float) -> float:
        if progress <= start:
            return 0.0
        contact_progress = (progress - start) / (1.0 - start)
        return math.sin(math.pi * contact_progress)

    if interaction == "head_pat":
        contact = contact_envelope(0.42)
        return InteractionFrame(
            offset_y=3.5 * contact ** 1.45,
            scale_x=1.0 + 0.020 * contact,
            scale_y=1.0 - 0.020 * contact,
        )

    if interaction == "cheek_poke":
        contact = contact_envelope(0.46)
        return InteractionFrame(
            offset_x=5.0 * contact,
            scale_x=1.0 - 0.020 * contact,
            scale_y=1.0 + 0.014 * contact,
            rotation=0.6 * contact,
        )

    if interaction == "hug":
        if progress < 0.32:
            approach = progress / 0.32
            closeness = approach * approach * (3.0 - 2.0 * approach)
        elif progress <= 0.72:
            closeness = 1.0
        else:
            retreat = (1.0 - progress) / 0.28
            closeness = retreat * retreat * (3.0 - 2.0 * retreat)
        elastic = math.sin(2.0 * math.pi * progress) * closeness
        return InteractionFrame(
            scale=1.0 + 0.58 * closeness,
            scale_x=1.0 + 0.012 * elastic,
            scale_y=1.0 - 0.009 * elastic,
        )

    contact = contact_envelope(0.38)
    wobble = math.sin(3.0 * math.pi * progress) * contact
    return InteractionFrame(
        offset_x=2.5 * wobble,
        offset_y=1.2 * contact,
        scale_x=1.0 + 0.012 * contact,
        scale_y=1.0 - 0.010 * contact,
        rotation=1.4 * wobble,
    )
