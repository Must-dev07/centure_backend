"""factory_boy fixtures for all core models."""
import factory
from django.utils import timezone

from babies.models import Baby
from bracelets.models import Bracelet
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


class BraceletFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Bracelet

    serial_number = factory.Sequence(lambda n: f"SB-{n:08d}")
    firmware_version = "1.0.0"
    status = Bracelet.Status.INACTIVE


class MeasurementFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Measurement

    baby = factory.SubFactory(BabyFactory)
    bracelet = factory.SubFactory(BraceletFactory)
    heart_rate = 130.0
    temperature = 37.0
    spo2 = 98.0
    movement = {"accel": [0.1, 0.2, 9.8], "gyro": [0, 0, 0], "magnitude": 0.4}
    battery = 80.0
    skin_contact = True
    recorded_at = factory.LazyFunction(timezone.now)
