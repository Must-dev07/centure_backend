"""NotificationChannel interface + fully-implemented FCM push channel.

SMS/email channels can be dropped in later by subclassing NotificationChannel
and adding them to CHANNELS — the dispatch pipeline is channel-agnostic.

FCM uses the HTTP v1 API with a Google service-account file
(FCM_SERVICE_ACCOUNT_FILE / FCM_PROJECT_ID env vars — see .env.example).
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


class NotificationChannel(ABC):
    """One implementation per delivery medium (push / sms / email)."""

    name: str

    @abstractmethod
    def send(self, notification) -> bool:
        """Deliver the notification. Return True on success."""


class FCMPushChannel(NotificationChannel):
    name = "push"
    FCM_ENDPOINT = "https://fcm.googleapis.com/v1/projects/{project}/messages:send"
    SCOPES = ["https://www.googleapis.com/auth/firebase.messaging"]

    def _access_token(self) -> str | None:
        """OAuth2 token from the service-account file. Returns None (and the
        notification is marked failed) if credentials are not configured."""
        sa_file = settings.FCM_SERVICE_ACCOUNT_FILE
        if not sa_file:
            logger.warning("FCM not configured (FCM_SERVICE_ACCOUNT_FILE unset)")
            return None
        from google.auth.transport.requests import Request
        from google.oauth2 import service_account

        creds = service_account.Credentials.from_service_account_file(
            sa_file, scopes=self.SCOPES
        )
        creds.refresh(Request())
        return creds.token

    def send(self, notification) -> bool:
        from notifications.models import DeviceToken

        token = self._access_token()
        if token is None:
            return False
        tokens = list(
            DeviceToken.objects.filter(user_id=notification.user_id).values_list(
                "token", flat=True
            )[:20]
        )
        if not tokens:
            logger.info("No device tokens for user %s", notification.user_id)
            return False

        url = self.FCM_ENDPOINT.format(project=settings.FCM_PROJECT_ID)
        ok = False
        for device_token in tokens:
            payload = {
                "message": {
                    "token": device_token,
                    "notification": {
                        "title": notification.title,
                        "body": notification.body,
                    },
                    "data": {
                        # Deep-link target for the mobile app (Alert Details screen)
                        "alert_id": str(notification.alert_id or ""),
                        "type": "alert",
                    },
                    "android": {"priority": "HIGH"},
                    "apns": {"headers": {"apns-priority": "10"}},
                }
            }
            try:
                resp = requests.post(
                    url,
                    json=payload,
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=10,
                )
                if resp.status_code == 200:
                    ok = True
                elif resp.status_code in (404, 410):
                    # Stale token — clean it up.
                    DeviceToken.objects.filter(token=device_token).delete()
                else:
                    logger.error("FCM error %s: %s", resp.status_code, resp.text[:300])
            except requests.RequestException:
                logger.exception("FCM request failed")
        return ok


# Registry: channel name -> implementation. SMS/email are drop-in later.
CHANNELS: dict[str, NotificationChannel] = {
    FCMPushChannel.name: FCMPushChannel(),
}
