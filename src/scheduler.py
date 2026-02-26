import json
import logging
from datetime import datetime, timezone
from typing import List, Optional
from pydantic import BaseModel
from src.config import (
    SCHEDULER_STATE_FILE,
    CLEANUP_CATEGORIES,
    CLEANUP_LOOKBACK_DAYS,
    CLEANUP_CRON_HOUR,
    CLEANUP_CRON_MINUTE,
)

logger = logging.getLogger(__name__)


class CategoryResult(BaseModel):
    category: str
    fetched: int
    deleted: int
    error: Optional[str] = None


class RunRecord(BaseModel):
    timestamp: str
    success: bool
    categories: List[CategoryResult]
    total_deleted: int


class SchedulerState(BaseModel):
    categories: List[str] = CLEANUP_CATEGORIES
    lookback_days: int = CLEANUP_LOOKBACK_DAYS
    cron_hour: int = CLEANUP_CRON_HOUR
    cron_minute: int = CLEANUP_CRON_MINUTE
    last_run: Optional[RunRecord] = None
    run_history: List[RunRecord] = []


class SchedulerManager:
    def __init__(self, state_file: str = SCHEDULER_STATE_FILE):
        self.state_file = state_file
        self.state = self._load()

    def _load(self) -> SchedulerState:
        try:
            with open(self.state_file, "r") as f:
                data = json.load(f)
            return SchedulerState(**data)
        except FileNotFoundError:
            return SchedulerState()
        except Exception as e:
            logger.error(f"Failed to load scheduler state: {e}")
            return SchedulerState()

    def _save(self):
        try:
            with open(self.state_file, "w") as f:
                json.dump(self.state.model_dump(), f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save scheduler state: {e}")

    def update_config(
        self,
        categories: Optional[List[str]] = None,
        lookback_days: Optional[int] = None,
        cron_hour: Optional[int] = None,
        cron_minute: Optional[int] = None,
    ):
        if categories is not None:
            self.state.categories = categories
        if lookback_days is not None:
            self.state.lookback_days = lookback_days
        if cron_hour is not None:
            self.state.cron_hour = cron_hour
        if cron_minute is not None:
            self.state.cron_minute = cron_minute
        self._save()

    def record_run(self, run: RunRecord):
        self.state.last_run = run
        self.state.run_history.append(run)
        # Keep only the last 10 runs
        if len(self.state.run_history) > 10:
            self.state.run_history = self.state.run_history[-10:]
        self._save()

    def get_status(self) -> dict:
        return {
            "last_run": self.state.last_run.model_dump() if self.state.last_run else None,
            "config": {
                "categories": self.state.categories,
                "lookback_days": self.state.lookback_days,
                "cron_hour": self.state.cron_hour,
                "cron_minute": self.state.cron_minute,
            },
        }


class CleanupJob:
    def run(self, gmail_client, scheduler_manager: SchedulerManager):
        import datetime as dt

        state = scheduler_manager.state
        now = datetime.now(timezone.utc)
        end_date = now.strftime("%Y-%m-%d")
        start_date = (now - dt.timedelta(days=state.lookback_days)).strftime("%Y-%m-%d")

        category_results: List[CategoryResult] = []
        total_deleted = 0
        overall_success = True

        logger.info(f"Starting cleanup job for categories: {state.categories}")

        for category in state.categories:
            try:
                emails = gmail_client.fetch_user_emails(
                    start_date=start_date,
                    end_date=end_date,
                    category=category,
                )
                fetched = len(emails)

                if not emails:
                    category_results.append(
                        CategoryResult(category=category, fetched=0, deleted=0)
                    )
                    continue

                cache = {category: emails}
                deleted = gmail_client.delete_user_emails(cache, category)
                total_deleted += deleted

                category_results.append(
                    CategoryResult(category=category, fetched=fetched, deleted=deleted)
                )
                logger.info(f"Category {category}: fetched={fetched}, deleted={deleted}")

            except Exception as e:
                logger.error(f"Error processing category {category}: {e}")
                overall_success = False
                category_results.append(
                    CategoryResult(category=category, fetched=0, deleted=0, error=str(e))
                )

        run = RunRecord(
            timestamp=now.isoformat(),
            success=overall_success,
            categories=category_results,
            total_deleted=total_deleted,
        )
        scheduler_manager.record_run(run)
        logger.info(f"Cleanup job complete. Total deleted: {total_deleted}")
        return run
