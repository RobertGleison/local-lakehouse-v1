from dagster import ScheduleDefinition
from core.dagster.jobs import bronze_ingestion_job

bronze_ingestion_daily = ScheduleDefinition(
    name="bronze_ingestion_daily",
    cron_schedule="0 6 * * *",
    job=bronze_ingestion_job,
    execution_timezone="UTC",
)
