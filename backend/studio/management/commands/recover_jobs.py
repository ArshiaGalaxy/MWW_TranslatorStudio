"""Mark orphaned jobs/projects as failed after a server restart.

Jobs run as daemon threads with in-memory locks, so after a restart every
non-terminal Job row is dead and every Project stuck in a working status is
stalled. Run this at startup (after migrate):

    python manage.py recover_jobs

Use --min-age-seconds to only reap rows older than N seconds when running
against a live server (ad-hoc debugging).
"""

from __future__ import annotations

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from studio.models import Job, Project

# Projects left in these statuses by a dead thread.
_BUSY_STATUSES = (
    Project.Status.EXTRACTING,
    Project.Status.TRANSLATING,
    Project.Status.APPLYING,
)


class Command(BaseCommand):
    help = "Mark jobs interrupted by a server restart as failed and unstick projects"

    def add_arguments(self, parser):
        parser.add_argument(
            "--min-age-seconds",
            type=int,
            default=0,
            help="Only reap jobs/projects updated at least this long ago",
        )

    def handle(self, *args, **options):
        min_age = options["min_age_seconds"]
        cutoff = timezone.now() - timedelta(seconds=min_age)

        stale_jobs = Job.objects.exclude(
            status__in=[Job.Status.SUCCESS, Job.Status.FAILED, Job.Status.CANCELLED]
        ).filter(updated_at__lte=cutoff)

        # Recovered projects: those that had results survive (pages exist) go
        # back to READY; otherwise they are no further along than CREATED.
        recovered = 0
        for project in Project.objects.filter(status__in=_BUSY_STATUSES):
            if project.updated_at > cutoff:
                continue
            project.status = (
                Project.Status.READY if project.pages.exists()
                else Project.Status.CREATED
            )
            project.error_message = "Interrupted by server restart"
            project.save(update_fields=["status", "error_message"])
            recovered += 1

        # Partial work from jobs killed by the restart (e.g. a translate that
        # had already saved some translations) must show up in the counters,
        # or the project looks untranslatable ("0 / N", rendering locked).
        # Capture the affected project ids BEFORE the update — afterwards the
        # queryset (non-terminal jobs only) matches nothing.
        from studio.services import _refresh_counts

        stale_project_pks = set(
            stale_jobs.values_list("project_id", flat=True))
        count = stale_jobs.update(
            status=Job.Status.FAILED,
            stage="Interrupted",
            error_message="Interrupted by server restart",
            finished_at=timezone.now(),
        )

        for pk in stale_project_pks:
            try:
                project = Project.objects.get(pk=pk)
            except Project.DoesNotExist:
                continue
            _refresh_counts(project)

        self.stdout.write(
            self.style.SUCCESS(
                f"recover_jobs: marked {count} job(s) failed, "
                f"recovered {recovered} project(s)"
            )
        )
