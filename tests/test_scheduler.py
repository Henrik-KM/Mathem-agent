from mathem_agent.scheduler import CRON_BEGIN, CRON_END, _without_cron_block


def test_existing_crontab_entries_are_preserved():
    original = "\n".join(
        [
            "15 7 * * * /home/user/backup.sh",
            CRON_BEGIN,
            "0 9 * * * /old/mathem-runner.sh",
            CRON_END,
            "30 8 * * 1 /home/user/report.sh",
        ]
    )
    cleaned = _without_cron_block(original)
    assert "/home/user/backup.sh" in cleaned
    assert "/home/user/report.sh" in cleaned
    assert "old/mathem-runner" not in cleaned
    assert CRON_BEGIN not in cleaned
    assert CRON_END not in cleaned
