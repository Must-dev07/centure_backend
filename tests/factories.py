"""factory_boy fixtures for all core models."""
import factory
from django.utils import timezone

from babies.models import Baby
from belts.models import belt
from invitations.models import Invitation
from invitations.services import generate_token, invitation_expiry
from measurements.models import Measurement
from users.models import Doctor, Parent, User


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User

    email = factory.Sequence(lambda n: f"user{n}@example.com")
    first_name = "Test"
    last_name = factory.Sequence(lambda n: f"User{n}")
    role = "parent"
    password = factory.PostGenerationMethodCall("set_password", "S3curePassw0rd!")


class AdminFactory(UserFactory):
    role = "admin"
    is_staff = True
    is_superuser = True


class ParentFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Parent

    user = factory.SubFactory(UserFactory, role="parent")
    address = "1 Rue des Lilas, Paris"
    emergency_contact = "+33600000000"


class DoctorFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Doctor

    user = factory.SubFactory(UserFactory, role="doctor")
    license_number = factory.Sequence(lambda n: f"LIC-{n:06d}")
    specialty = "Neonatology"


class BabyFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Baby

    name = factory.Sequence(lambda n: f"Baby{n}")
    birth_date = factory.LazyFunction(lambda: timezone.now().date())
    weight_grams = 3200
    gender = "female"
    parent = factory.SubFactory(ParentFactory)
    assigned_doctor = factory.SubFactory(DoctorFactory)
    enrollment_reason = Baby.EnrollmentReason.PREMATURITY
    # Enrolled by the assigned doctor when there is one, otherwise by an admin.
    enrolled_by = factory.LazyAttribute(
        lambda o: o.assigned_doctor.user if o.assigned_doctor else AdminFactory()
    )


class InvitationFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Invitation

    email = factory.Sequence(lambda n: f"invitee{n}@example.com")
    token = factory.LazyFunction(generate_token)
    status = Invitation.Status.PENDING
    created_by = factory.SubFactory(AdminFactory)
    expires_at = factory.LazyFunction(invitation_expiry)


class beltFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = belt

    serial_number = factory.Sequence(lambda n: f"SB-{n:08d}")
    firmware_version = "1.0.0"
    status = belt.Status.INACTIVE


class MeasurementFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Measurement

    baby = factory.SubFactory(BabyFactory)
    belt = factory.SubFactory(beltFactory)
    # Older child at rest — all within normal range.
    heart_rate = 85.0
    temperature = 37.2
    respiratory_rate = 22.0
    battery = 80.0
    skin_contact = True
    activity = "rest"
    recorded_at = factory.LazyFunction(timezone.now)
