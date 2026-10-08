"""Phase 1 migrations: legacy backfill (owner decisions) and model/migration
consistency. Runs against the pytest test database only."""
from datetime import date
from io import StringIO

import pytest
from django.core.management import call_command
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

BABIES_BEFORE_REFONTE = ("babies", "0003_doctorassignmentrequest")
# Migration targets: babies back to 0003 and the invitations app unapplied.
BEFORE_REFONTE = [BABIES_BEFORE_REFONTE, ("invitations", None)]
LEGACY_NOTE = "Legacy enrollment — original enrollment reason was not recorded."


def _migrate(targets):
    executor = MigrationExecutor(connection)
    executor.loader.build_graph()
    executor.migrate(targets)
    return executor


def _leaf_nodes():
    executor = MigrationExecutor(connection)
    return executor.loader.graph.leaf_nodes()


@pytest.mark.django_db(transaction=True)
def test_legacy_babies_backfilled():
    leaves = _leaf_nodes()
    executor = _migrate(BEFORE_REFONTE)
    try:
        old = executor.loader.project_state([BABIES_BEFORE_REFONTE]).apps
        User = old.get_model("users", "User")
        Parent = old.get_model("users", "Parent")
        Baby = old.get_model("babies", "Baby")

        parent_user = User.objects.create(email="legacy.parent@example.com", role="parent", password="!")
        parent = Parent.objects.create(user=parent_user)
        for name in ("Ancien 1", "Ancien 2"):
            Baby.objects.create(
                name=name, birth_date=date(2026, 1, 1), weight_grams=3000, gender="female", parent=parent
            )

        # Babies exist but no Doctor/Admin/superuser: the backfill refuses to invent one.
        with pytest.raises(RuntimeError, match="no Doctor/Admin user"):
            _migrate(leaves)

        inactive_admin = User.objects.create(email="old.admin@example.com", role="admin", is_active=False, password="!")
        doctor = User.objects.create(email="doctor@example.com", role="doctor", password="!")
        User.objects.create(email="admin@example.com", role="admin", password="!")
        assert inactive_admin.id < doctor.id

        executor = _migrate(leaves)
        new = executor.loader.project_state(leaves).apps
        NewBaby = new.get_model("babies", "Baby")
        babies = list(NewBaby.objects.order_by("id"))
        assert len(babies) == 2
        for baby in babies:
            assert baby.enrollment_reason == "other"
            assert baby.enrollment_notes == LEGACY_NOTE
            assert baby.gestational_age_weeks is None
            assert baby.enrolled_by_id == doctor.id  # first active Doctor/Admin by id
            assert baby.parent_id == parent.id  # existing links untouched
        # No enrollment history entries are backfilled for legacy babies.
        assert new.get_model("babies", "MedicalHistoryEntry").objects.count() == 0
    finally:
        _migrate(_leaf_nodes())


@pytest.mark.django_db(transaction=True)
def test_backfill_falls_back_to_superuser():
    leaves = _leaf_nodes()
    executor = _migrate(BEFORE_REFONTE)
    try:
        old = executor.loader.project_state([BABIES_BEFORE_REFONTE]).apps
        User = old.get_model("users", "User")
        Parent = old.get_model("users", "Parent")
        Baby = old.get_model("babies", "Baby")
        parent = Parent.objects.create(
            user=User.objects.create(email="p@example.com", role="parent", password="!")
        )
        Baby.objects.create(name="B", birth_date=date(2026, 1, 1), weight_grams=3000, parent=parent)
        superuser = User.objects.create(
            email="root@example.com", role="parent", is_superuser=True, password="!"
        )

        executor = _migrate(leaves)
        NewBaby = executor.loader.project_state(leaves).apps.get_model("babies", "Baby")
        assert NewBaby.objects.get().enrolled_by_id == superuser.id
    finally:
        _migrate(_leaf_nodes())


@pytest.mark.django_db(transaction=True)
def test_refonte_migrations_reverse_cleanly_without_parentless_babies():
    leaves = _leaf_nodes()
    try:
        _migrate(BEFORE_REFONTE)  # reverse 0004–0006 and invitations.0001
        _migrate(leaves)
    finally:
        _migrate(_leaf_nodes())


@pytest.mark.django_db
def test_no_missing_migrations():
    out = StringIO()
    try:
        call_command("makemigrations", "--check", "--dry-run", stdout=out, stderr=out)
    except SystemExit:  # --check exits non-zero when changes are detected
        pytest.fail(f"Model changes without migrations:\n{out.getvalue()}")
