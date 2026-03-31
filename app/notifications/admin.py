from django.contrib import admin
from django.contrib.auth.models import Group, User

from .models import NotificationTemplate, NotificationDelivery


@admin.register(NotificationTemplate)
class NotificationTemplateAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "name",
        "priority",
        "retry_count",
        "retry_delay_minutes",
        "is_active",
        "created_at",
        "updated_at",
    )
    list_filter = ("priority", "is_active", "created_at", "updated_at")
    search_fields = ("name", "message_template")
    readonly_fields = ("created_at", "updated_at")
    ordering = ("priority", "name")


@admin.register(NotificationDelivery)
class NotificationDeliveryAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "event",
        "template",
        "notification_type",
        "recipient_address",
        "status",
        "attempt_count",
        "last_attempt_at",
        "sent_at",
        "created_at",
    )
    list_filter = (
        "status",
        "notification_type",
        "created_at",
        "sent_at",
        "last_attempt_at",
    )
    search_fields = (
        "event",
        "template",
        "recipient_address",
        "recipient_name",
        "rendered_message",
        "error_message",
    )
    readonly_fields = ("created_at",)
    ordering = ("status", "-created_at")


admin.site.unregister(Group)
admin.site.unregister(User)