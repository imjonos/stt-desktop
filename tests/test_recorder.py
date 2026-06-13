import unittest

import numpy as np

from app.recorder import Recorder, _resample_to_target


class FakeConnection:
    def poll(self, _timeout):
        return False


class FakeCrashedProcess:
    exitcode = -1073741819

    def is_alive(self):
        return False


class RecorderTest(unittest.TestCase):
    def test_resamples_audio_to_target_rate(self):
        source = np.linspace(-1.0, 1.0, 48000, dtype=np.float32).reshape(-1, 1)

        result = _resample_to_target(source, 48000, 16000)

        self.assertEqual(result.shape, (16000, 1))
        self.assertEqual(result.dtype, np.float32)

    def test_reports_native_recorder_crash_without_exiting_parent(self):
        recorder = Recorder()
        recorder._connection = FakeConnection()
        recorder._process = FakeCrashedProcess()

        with self.assertRaisesRegex(RuntimeError, "audio-crash.log"):
            recorder._receive_message(0.1, "запуска микрофона")


if __name__ == "__main__":
    unittest.main()
