from apscheduler.schedulers.background import BackgroundScheduler

from . import db
from .services.schedule_runner import run_schedule_now


def create_scheduler() -> BackgroundScheduler:
    scheduler = BackgroundScheduler(timezone="Asia/Seoul")
    scheduler.add_job(
        record_scheduler_heartbeat,
        "interval",
        minutes=30,
        id="scheduler_heartbeat",
        replace_existing=True,
    )
    register_daily_schedule_jobs(scheduler)
    return scheduler


def register_daily_schedule_jobs(scheduler: BackgroundScheduler) -> None:
    for schedule in db.list_rows("schedule"):
        if not schedule.get("enabled"):
            continue
        hour_minute = _daily_hour_minute(schedule.get("cron", ""))
        if hour_minute is None:
            continue
        hour, minute = hour_minute
        scheduler.add_job(
            run_schedule_now,
            "cron",
            hour=hour,
            minute=minute,
            id=f"schedule_{schedule['id']}",
            args=[schedule["id"]],
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )


def record_scheduler_heartbeat() -> None:
    db.insert(
        "notification_log",
        {
            "channel": "scheduler",
            "target": "system",
            "title": "scheduler heartbeat",
            "body": "APScheduler heartbeat recorded.",
            "payload": {"kind": "heartbeat"},
            "status": "recorded",
            "error": None,
            "created_at": db.utc_now(),
        },
    )


def _daily_hour_minute(cron: str):
    prefix = "매일 "
    if not cron.startswith(prefix):
        return None
    time_part = cron[len(prefix):].split()[0]
    if ":" not in time_part:
        return None
    hour, minute = time_part.split(":", 1)
    try:
        return int(hour), int(minute)
    except ValueError:
        return None
