import json

from cnc_controller.ui.motion import MotionController, MotionMode


class ValueTarget:
    def __init__(self, value=0):
        self._value = value

    def value(self):
        return self._value

    def setValue(self, value):
        self._value = value


def test_motion_mode_persists(tmp_path):
    path = tmp_path / "motion.json"
    controller = MotionController(config_path=path)

    controller.set_mode(MotionMode.REDUCED)

    assert json.loads(path.read_text()) == {"mode": "reduced"}
    assert MotionController(config_path=path).mode is MotionMode.REDUCED


def test_invalid_motion_config_uses_standard(tmp_path):
    path = tmp_path / "motion.json"
    path.write_text('{"mode": "turbo"}')

    controller = MotionController(config_path=path)

    assert controller.mode is MotionMode.STANDARD
    assert controller.duration == controller.STANDARD_DURATION


def test_motion_off_updates_value_immediately(tmp_path):
    controller = MotionController(config_path=tmp_path / "motion.json")
    controller.set_mode(MotionMode.OFF)
    target = ValueTarget(10)

    controller.animate_value(target, 80)

    assert target.value() == 80
    assert controller.duration == 0
