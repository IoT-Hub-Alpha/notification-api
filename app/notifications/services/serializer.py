from dataclasses import dataclass
from typing import Optional, Any
from notifications.services.exceptions import ApiValidationError
from notifications.models import NotificationTemplate, NotificationDelivery
from django.forms.models import model_to_dict
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction


@dataclass
class NotifTemplateSerializer:
    instance: Optional[NotificationTemplate] = None

    read_fields = (
        "id",
        "name",
        "message_template",
        "recipients",
        "priority",
        "retry_count",
        "retry_delay_minutes",
        "is_active",
        "created_at",
    )

    def to_dict(self) -> dict[str, Any]:
        if self.instance is None:
            raise ValueError(
                "NotifTemplateSerializer(instance=...) is required for to_dict()"
            )

        payload = model_to_dict(self.instance, fields=self.read_fields)

        for k in ("created_at", "updated_at"):
            dt = getattr(self.instance, k, None)
            payload[k] = dt.isoformat() if dt else None

        return payload


@dataclass
class NotifDeliverySerializer:
    instance: Optional[NotificationDelivery] = None

    read_fields = (
        "id",
        "event",
        "template",
        "notification_type",
        "recipient_address",
        "recipient_name",
        "rendered_message",
        "status",
        "attempt_count",
        "last_attempt_at",
        "error_message",
        "sent_at",
        "created_at",
    )

    def to_dict(self) -> dict[str, Any]:
        if self.instance is None:
            raise ValueError(
                "NotifDeliverySerializer(instance=...) is required for to_dict()"
            )

        payload = model_to_dict(self.instance, fields=self.read_fields)

        for k in ("sent_at", "created_at", "last_attempt_at"):
            dt = getattr(self.instance, k, None)
            payload[k] = dt.isoformat() if dt else None

        return payload


def template_update(instance, data: dict[str, Any]) -> "NotificationTemplate":
    ALLOWED_FIELDS_UPDATE = {
        "name",
        "message_template",
        "recipients",
        "priority",
        "retry_count",
        "retry_delay_minutes",
        "is_active",
    }

    if not isinstance(data, dict):
        raise TypeError("data must be a dictionary")

    update_fields: list[str] = []

    for key, value in data.items():
        if key in ALLOWED_FIELDS_UPDATE:
            setattr(instance, key, value)
            update_fields.append(key)

    if not update_fields:
        return instance

    try:
        instance.full_clean()
        with transaction.atomic():
            instance.save(update_fields=update_fields)
    except ValidationError as exc:
        raise ApiValidationError({"errors": f"validation error {exc}"}, status_code=400)
    except IntegrityError as exc:
        raise ApiValidationError(
            {"errors": [f"Database integrity error: {exc}"]}
        ) from exc

    return instance
