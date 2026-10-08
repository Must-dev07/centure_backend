from django.urls import path

from .views import InvitationAcceptView, InvitationListView, InvitationResendView

urlpatterns = [
    path("", InvitationListView.as_view(), name="invitation-list"),
    path("<int:pk>/resend/", InvitationResendView.as_view(), name="invitation-resend"),
    path("<str:token>/accept/", InvitationAcceptView.as_view(), name="invitation-accept"),
]
