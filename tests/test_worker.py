import app.worker as worker


def test_worker_module_has_no_side_effects_on_import():
    assert worker.INTERVAL_SECONDS == 60
    assert isinstance(worker.LOCK_KEY, int)
    assert callable(worker.main)