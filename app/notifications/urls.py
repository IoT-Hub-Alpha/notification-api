from django.urls import path

from .views import NotificationDeliveryListView, NotificationTemplateListView, GetHealth

urlpatterns = [
    path(
        "v1/notifications/notification_template/",
        NotificationTemplateListView.as_view(),
        name="Notification_template_view",
    ),
    path(
        "v1/notifications/notification_delivery/",
        NotificationDeliveryListView.as_view(),
        name="Notification_delivery_view",
    ),
    path(
        "health",
        GetHealth.as_view(),
        name="get_health"
    )
]
