from app.backtest import executor


def test_submit_backtest_allows_worker_run_id_keyword():
    """The executor job key must not collide with a worker's run_id argument."""

    job_id = 123
    future = executor.submit_backtest(
        job_id,
        lambda *, run_id: run_id,
        run_id=job_id,
    )

    try:
        assert future.result(timeout=5) == job_id
        assert executor._jobs[job_id] is future
    finally:
        executor.cleanup_job(job_id)
