import unittest

from resona_desktop_pet.interaction_effects import (
    INTERACTION_DURATIONS_MS,
    InteractionFrame,
    sample_interaction,
)


class InteractionEffectsTests(unittest.TestCase):
    def test_every_interaction_has_duration(self):
        expected = {"head_pat", "cheek_poke", "hug", "shoulder_pat"}
        self.assertEqual(expected, set(INTERACTION_DURATIONS_MS))
        self.assertTrue(all(INTERACTION_DURATIONS_MS[name] >= 1400 for name in expected))

    def test_all_animations_start_and_finish_neutral(self):
        neutral = InteractionFrame()
        for interaction in INTERACTION_DURATIONS_MS:
            with self.subTest(interaction=interaction):
                self.assertEqual(neutral, sample_interaction(interaction, 0.0))
                self.assertEqual(neutral, sample_interaction(interaction, 1.0))

    def test_gestures_are_visibly_distinct(self):
        samples = [index / 100.0 for index in range(101)]
        head_dip = max(sample_interaction("head_pat", p).offset_y for p in samples)
        cheek_shift = max(sample_interaction("cheek_poke", p).offset_x for p in samples)
        hug_scale = max(sample_interaction("hug", p).scale for p in samples)
        shoulder_tilt = max(abs(sample_interaction("shoulder_pat", p).rotation) for p in samples)

        self.assertGreater(head_dip, 3.2)
        self.assertLessEqual(head_dip, 3.6)
        self.assertGreater(cheek_shift, 4.7)
        self.assertLessEqual(cheek_shift, 5.1)
        self.assertGreater(hug_scale, 1.57)
        self.assertLessEqual(hug_scale, 1.581)
        self.assertGreater(shoulder_tilt, 0.8)
        self.assertLessEqual(shoulder_tilt, 1.5)

    def test_contact_frames_add_subtle_squash_and_stretch(self):
        samples = [index / 100.0 for index in range(101)]
        head = [sample_interaction("head_pat", p) for p in samples]
        cheek = [sample_interaction("cheek_poke", p) for p in samples]
        self.assertGreater(max(frame.scale_x for frame in head), 1.015)
        self.assertLess(min(frame.scale_y for frame in head), 0.985)
        self.assertLess(min(frame.scale_x for frame in cheek), 0.985)
        self.assertGreater(max(frame.scale_y for frame in cheek), 1.01)

    def test_unknown_interaction_is_safe_and_neutral(self):
        self.assertEqual(InteractionFrame(), sample_interaction("unknown", 0.5))


if __name__ == "__main__":
    unittest.main()
