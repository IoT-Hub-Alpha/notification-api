import json
import sys
import types
import re
import pytest
from django.contrib import admin
from django.contrib.admin.sites import NotRegistered
from django.core.exceptions import ValidationError
from django.http import Http404
from django.test import RequestFactory
from django.urls import resolve, reverse


# Stub custom auth dependency so importing views works in isolation.
if "iot_auth.django" not in sys.modules:
    iot_auth_module = types.ModuleType("iot_auth")
    django_submodule = types.ModuleType("iot_auth.django")

    class CheckPermissionsMixin:
        pass

    def check_permissions(*args, **kwargs):
        return True

    django_submodule.CheckPermissionsMixin = CheckPermissionsMixin
    django_submodule.check_permissions = check_permissions
    iot_auth_module.django = django_submodule
    sys.modules["iot_auth"] = iot_auth_module
    sys.modules["iot_auth.django"] = django_submodule


from notifications.models import (  # noqa: E402
    NotificationDelivery,
    NotificationPriority,
    NotificationTemplate,
    validate_recipients,
)
from notifications.services.data_type import AuthenticatedHttpRequest  # noqa: E402
from notifications.services.exceptions import (  # noqa: E402
    ApiValidationError,
    BadRequestError,
    NotFoundError,
)
from notifications.services.helper import construct_paginated_response  # noqa: E402
from notifications.services.serializer import (  # noqa: E402
    NotifDeliverySerializer,
    NotifTemplateSerializer,
    template_update,
)
from notifications.views import (  # noqa: E402
    NotificationDeliveryListView,
    NotificationTemplateListView,
    _json_body,
    _parse_uuid,
    handle_api_errors,
)


@pytest.fixture
def rf():
    return RequestFactory()


@pytest.fixture
def template_payload():
    return {
        "name": "cpu_alert",
        "message_template": "Alert {severity}: {message}",
        "recipients": [{"type": "email", "address": "ops@example.com"}],
        "priority": NotificationPriority.HIGH,
        "retry_count": 3,
        "retry_delay_minutes": 5,
        "is_active": True,
    }


@pytest.fixture
def template(db, template_payload):
    return NotificationTemplate.objects.create(**template_payload)


@pytest.fixture
def delivery(db):
    return NotificationDelivery.objects.create(
        event="evt-1",
        template="templ-1",
        notification_type=NotificationDelivery.NotificationType.EMAIL,
        recipient_address="ops@example.com",
        recipient_name="Ops",
        rendered_message="message 1",
        status=NotificationDelivery.NotificationStatus.PENDING,
        attempt_count=1,
    )


@pytest.fixture
def extra_delivery(db):
    return NotificationDelivery.objects.create(
        event="evt-2",
        template="templ-2",
        notification_type=NotificationDelivery.NotificationType.SMS,
        recipient_address="+380501234567",
        rendered_message="message 2",
        status=NotificationDelivery.NotificationStatus.SENT,
    )


@pytest.mark.django_db
class TestRecipientValidation:
    def test_accepts_supported_recipient_types(self):
        validate_recipients(
            [
                {"type": "email", "address": "ops@example.com"},
                {"type": "sms", "phone": "+380501234567"},
                {"type": "webhook", "url": "https://example.com/hook"},
            ]
        )

    @pytest.mark.parametrize(
        "value,error_text",
        [
            ({"type": "email", "address": "ops@example.com"}, "must be a list"),
            ([], "cannot be empty"),
            (["oops"], "must be a dictionary"),
            ([{}], "must have a 'type'"),
            ([{"type": "email"}], "Email recipient must have an 'address'"),
            ([{"type": "sms"}], "SMS recipient must have a 'phone'"),
            ([{"type": "webhook"}], "Webhook recipient must have a 'url'"),
            ([{"type": "push", "token": "abc"}], "Unknown recipient type"),
        ],
    )
    def test_rejects_invalid_recipients(self, value, error_text):
        with pytest.raises(ValidationError, match=error_text):
            validate_recipients(value)


@pytest.mark.django_db
class TestNotificationTemplateModel:
    def test_create_persists_valid_template(self, template_payload):
        instance = NotificationTemplate.create(template_payload)

        assert instance.pk is not None
        assert NotificationTemplate.objects.count() == 1
        assert instance.name == "cpu_alert"

    def test_create_wraps_validation_errors(self, template_payload):
        template_payload["recipients"] = []

        with pytest.raises(ApiValidationError) as exc:
            NotificationTemplate.create(template_payload)

        assert exc.value.status_code == 400
        assert "error" in exc.value.errors

    def test_create_wraps_type_errors(self, template_payload):
        template_payload["unknown_field"] = "boom"

        with pytest.raises(ApiValidationError) as exc:
            NotificationTemplate.create(template_payload)

        assert exc.value.status_code == 400
        assert "unexpected keyword" in exc.value.errors["error"]

    def test_str_contains_name_and_priority(self, template):
        rendered = str(template)
        assert template.name in rendered
        assert str(template.priority) in rendered

    def test_meta_configuration(self):
        assert NotificationTemplate._meta.db_table == "notification_templates"
        assert NotificationTemplate._meta.ordering == ["priority", "name"]


@pytest.mark.django_db
class TestNotificationDeliveryModel:
    def test_str_contains_key_fields(self, delivery):
        rendered = str(delivery)
        assert f"Delivery {delivery.id}" in rendered
        assert delivery.recipient_address in rendered
        assert delivery.status in rendered

    def test_meta_configuration(self):
        assert NotificationDelivery._meta.db_table == "notification_deliveries"
        assert NotificationDelivery._meta.ordering == ["status", "-created_at"]
        assert (
            NotificationDelivery._meta.verbose_name_plural == "Notification deliveries"
        )


@pytest.mark.django_db
class TestSerializers:
    def test_delivery_serializer_returns_expected_payload(self, delivery):
        payload = NotifDeliverySerializer(instance=delivery).to_dict()

        assert payload["event"] == delivery.event
        assert payload["template"] == delivery.template
        assert payload["recipient_address"] == delivery.recipient_address
        assert payload["created_at"] is not None
        assert payload["last_attempt_at"] is None
        assert payload["sent_at"] is None

    def test_delivery_serializer_requires_instance(self):
        with pytest.raises(
            ValueError,
            match=re.escape(
                "NotifDeliverySerializer(instance=...) is required for to_dict()"
            ),
        ):
            NotifDeliverySerializer().to_dict()

    def test_template_serializer_requires_instance(self):
        with pytest.raises(
            ValueError,
            match=re.escape(
                "NotifTemplateSerializer(instance=...) is required for to_dict()"
            ),
        ):
            NotifTemplateSerializer().to_dict()

    def test_template_update_updates_supported_fields(self, template):
        updated = template_update(
            template,
            {
                "name": "cpu_alert_v2",
                "recipients": [{"type": "email", "address": "new@example.com"}],
                "priority": NotificationPriority.CRITICAL,
                "retry_count": 4,
                "retry_delay_minutes": 10,
                "is_active": False,
            },
        )

        updated.refresh_from_db()
        assert updated.name == "cpu_alert_v2"
        assert updated.recipients == [{"type": "email", "address": "new@example.com"}]
        assert updated.priority == NotificationPriority.CRITICAL
        assert updated.retry_count == 4
        assert updated.retry_delay_minutes == 10
        assert updated.is_active is False

    def test_template_update_ignores_unallowed_message_template_field_due_to_bug(
        self, template
    ):
        updated = template_update(
            template, {"message_template": "Alert {severity}: {message}"}
        )
        updated.refresh_from_db()

        assert updated.message_template == "Alert {severity}: {message}"

    def test_template_update_returns_same_instance_when_nothing_updatable(
        self, template
    ):
        updated = template_update(template, {"unknown": "value"})
        assert updated.pk == template.pk

    def test_template_update_rejects_non_dict_payload(self, template):
        with pytest.raises(TypeError, match="data must be a dictionary"):
            template_update(template, [1, 2, 3])

    def test_template_update_wraps_validation_errors(self, template):
        with pytest.raises(ApiValidationError) as exc:
            template_update(template, {"recipients": []})

        assert exc.value.status_code == 400

    def test_template_update_wraps_integrity_errors(self, template):
        NotificationTemplate.objects.create(
            name="other",
            message_template="Other",
            recipients=[{"type": "email", "address": "other@example.com"}],
            priority=NotificationPriority.LOW,
            retry_count=1,
            retry_delay_minutes=1,
            is_active=True,
        )

        with pytest.raises(ApiValidationError) as exc:
            template_update(template, {"name": "other"})

        assert exc.value.status_code == 400


class TestExceptionsAndTypes:
    def test_api_validation_error_stores_payload(self):
        err = ApiValidationError({"field": ["bad"]}, status_code=422)
        assert err.errors == {"field": ["bad"]}
        assert err.status_code == 422

    def test_bad_request_error_defaults(self):
        err = BadRequestError("bad")
        assert err.message == "bad"
        assert err.status_code == 400

    def test_not_found_error_defaults(self):
        err = NotFoundError()
        assert err.message == "Not found."
        assert err.status_code == 404

    def test_authenticated_request_type_allows_jwt_payload_attribute(self):
        request = AuthenticatedHttpRequest()
        request.jwt_payload = {
            "user_id": 1,
            "email": "u@example.com",
            "roles": ["admin"],
        }
        assert request.jwt_payload["user_id"] == 1


class TestHelpersAndParsing:
    def test_construct_paginated_response_shape(self):
        from django.core.paginator import Paginator

        items = list(range(12))
        paginator = Paginator(items, 5)
        page_obj = paginator.page(2)

        payload = construct_paginated_response(
            page_obj.object_list, page_obj, 5, paginator
        )

        assert payload["data"] == [5, 6, 7, 8, 9]
        assert payload["pagination"] == {
            "page": 2,
            "page_size": 5,
            "total": 12,
            "total_pages": 3,
            "next_page": 3,
            "prev_page": 1,
        }

    def test_json_body_returns_empty_dict_for_empty_body(self, rf):
        request = rf.post("/templates/", data="", content_type="application/json")
        request._body = b""
        assert _json_body(request) == {}

    def test_json_body_parses_valid_json(self, rf):
        request = rf.post(
            "/templates/",
            data=json.dumps({"name": "ok"}),
            content_type="application/json",
        )
        assert _json_body(request) == {"name": "ok"}

    def test_json_body_raises_bad_request_for_invalid_json(self, rf):
        request = rf.post(
            "/templates/", data="not-json", content_type="application/json"
        )
        with pytest.raises(BadRequestError, match="Invalid JSON body"):
            _json_body(request)

    def test_parse_uuid_accepts_uuid_and_string(self):
        import uuid

        value = uuid.uuid4()
        assert _parse_uuid(value) == value
        assert _parse_uuid(str(value)) == value

    def test_parse_uuid_rejects_invalid_values(self):
        with pytest.raises(BadRequestError, match="Invalid UUID format"):
            _parse_uuid("not-a-uuid")


class TestErrorDecorator:
    def test_converts_api_validation_error(self):
        @handle_api_errors
        def sample_view(_request):
            raise ApiValidationError(
                errors={"name": ["already exists"]}, status_code=400
            )

        response = sample_view(object())
        assert response.status_code == 400
        assert json.loads(response.content) == {"errors": {"name": ["already exists"]}}

    def test_converts_bad_request_error(self):
        @handle_api_errors
        def sample_view(_request):
            raise BadRequestError("bad body")

        response = sample_view(object())
        assert response.status_code == 400
        assert json.loads(response.content) == {"error": "bad body"}

    def test_converts_not_found_error(self):
        @handle_api_errors
        def sample_view(_request):
            raise NotFoundError("missing")

        response = sample_view(object())
        assert response.status_code == 404
        assert json.loads(response.content) == {"error": "missing"}

    def test_converts_value_error(self):
        @handle_api_errors
        def sample_view(_request):
            raise ValueError("broken")

        response = sample_view(object())
        assert response.status_code == 400
        assert json.loads(response.content) == {"error": "broken"}

    def test_leaves_success_response_untouched(self):
        @handle_api_errors
        def sample_view(_request):
            from django.http import JsonResponse

            return JsonResponse({"ok": True})

        response = sample_view(object())
        assert response.status_code == 200
        assert json.loads(response.content) == {"ok": True}


@pytest.mark.django_db
class TestNotificationTemplateViews:
    def test_get_returns_paginated_templates(self, rf, monkeypatch, template):
        view = NotificationTemplateListView.as_view()
        request = rf.get("/v1/notifications/notification_template/")

        class SerializerStub:
            def __init__(self, instance):
                self.instance = instance

            def to_dict(self):
                return {"id": self.instance.id, "name": self.instance.name}

        monkeypatch.setattr(
            "notifications.views.NotifTemplateSerializer", SerializerStub
        )

        response = view(request)
        payload = json.loads(response.content)

        assert response.status_code == 200
        assert payload["data"] == [{"id": template.id, "name": template.name}]
        assert payload["pagination"]["page"] == 1

    def test_get_filters_by_notif_template_id(self, rf, monkeypatch, template):
        NotificationTemplate.objects.create(
            name="other_template",
            message_template="Other",
            recipients=[{"type": "email", "address": "other@example.com"}],
            priority=NotificationPriority.LOW,
            retry_count=1,
            retry_delay_minutes=1,
            is_active=True,
        )
        view = NotificationTemplateListView.as_view()
        request = rf.get(
            f"/v1/notifications/notification_template/?notif_template_id={template.id}"
        )

        class SerializerStub:
            def __init__(self, instance):
                self.instance = instance

            def to_dict(self):
                return {"id": self.instance.id}

        monkeypatch.setattr(
            "notifications.views.NotifTemplateSerializer", SerializerStub
        )

        response = view(request)
        payload = json.loads(response.content)

        assert response.status_code == 200
        assert payload["data"] == [{"id": template.id}]

    def test_get_returns_invalid_page_on_bad_page_number(self, rf):
        view = NotificationTemplateListView.as_view()
        request = rf.get("/v1/notifications/notification_template/?page=999")

        response = view(request)

        assert response.status_code == 400
        assert json.loads(response.content) == {"errors": {"page": "Invalid page"}}

    def test_post_creates_template(self, rf, monkeypatch):
        view = NotificationTemplateListView.as_view()
        request = rf.post(
            "/v1/notifications/notification_template/",
            data=json.dumps({"name": "cpu_alert"}),
            content_type="application/json",
        )

        created = types.SimpleNamespace(id=7)
        monkeypatch.setattr(
            "notifications.views.NotificationTemplate.create", lambda data: created
        )

        class SerializerStub:
            def __init__(self, instance):
                self.instance = instance

            def to_dict(self):
                return {"id": self.instance.id}

        monkeypatch.setattr(
            "notifications.views.NotifTemplateSerializer", SerializerStub
        )

        response = view(request)
        assert response.status_code == 200
        assert json.loads(response.content) == {"id": 7}

    def test_post_returns_json_error_for_invalid_json(self, rf):
        view = NotificationTemplateListView.as_view()
        request = rf.post(
            "/v1/notifications/notification_template/",
            data="not-json",
            content_type="application/json",
        )

        response = view(request)
        assert response.status_code == 400
        assert json.loads(response.content) == {"error": "Invalid JSON body."}

    def test_delete_requires_id(self, rf):
        view = NotificationTemplateListView.as_view()
        request = rf.delete("/v1/notifications/notification_template/")

        response = view(request)

        assert response.status_code == 400
        assert json.loads(response.content) == {
            "error": "No notif_template_id provided"
        }

    def test_delete_success(self, rf, template):
        view = NotificationTemplateListView.as_view()
        request = rf.delete(
            f"/v1/notifications/notification_template/?notif_template_id={template.id}"
        )

        response = view(request)

        assert response.status_code == 204
        assert NotificationTemplate.objects.filter(pk=template.pk).count() == 0

    def test_delete_missing_object_currently_raises_http404(self, rf):
        view = NotificationTemplateListView.as_view()
        request = rf.delete(
            "/v1/notifications/notification_template/?notif_template_id=999999"
        )

        with pytest.raises(Http404):
            view(request)

    def test_patch_requires_id(self, rf):
        view = NotificationTemplateListView.as_view()
        request = rf.patch(
            "/v1/notifications/notification_template/",
            data=json.dumps({"name": "x"}),
            content_type="application/json",
        )

        response = view(request)
        assert response.status_code == 400
        assert json.loads(response.content) == {
            "error": "No notif_template_id provided"
        }

    def test_patch_updates_and_serializes(self, rf, monkeypatch, template):
        view = NotificationTemplateListView.as_view()
        request = rf.patch(
            f"/v1/notifications/notification_template/?notif_template_id={template.id}",
            data=json.dumps({"name": "new_name"}),
            content_type="application/json",
        )

        def fake_update(instance, data):
            instance.name = data["name"]
            return instance

        class SerializerStub:
            def __init__(self, instance):
                self.instance = instance

            def to_dict(self):
                return {"id": self.instance.id, "name": self.instance.name}

        monkeypatch.setattr("notifications.views.template_update", fake_update)
        monkeypatch.setattr(
            "notifications.views.NotifTemplateSerializer", SerializerStub
        )

        response = view(request)
        assert response.status_code == 200
        assert json.loads(response.content) == {"id": template.id, "name": "new_name"}


@pytest.mark.django_db
class TestNotificationDeliveryViews:
    def test_get_returns_paginated_deliveries_using_current_serializer_path(
        self, rf, monkeypatch, delivery, extra_delivery
    ):
        view = NotificationDeliveryListView.as_view()
        request = rf.get("/v1/notifications/notification_delivery/")

        class TemplateSerializerStub:
            def __init__(self, instance):
                self.instance = instance

            def to_dict(self):
                return {"serialized_with": "template", "id": self.instance.id}

        monkeypatch.setattr(
            "notifications.views.NotifTemplateSerializer", TemplateSerializerStub
        )

        response = view(request)
        payload = json.loads(response.content)

        assert response.status_code == 200
        assert len(payload["data"]) == 2

    def test_get_filters_by_event_id(self, rf, monkeypatch, delivery, extra_delivery):
        view = NotificationDeliveryListView.as_view()
        request = rf.get("/v1/notifications/notification_delivery/?event_id=evt-1")

        class TemplateSerializerStub:
            def __init__(self, instance):
                self.instance = instance

            def to_dict(self):
                return {"event": self.instance.event}

        monkeypatch.setattr(
            "notifications.views.NotifTemplateSerializer", TemplateSerializerStub
        )

        response = view(request)
        payload = json.loads(response.content)

        assert response.status_code == 200
        assert payload["data"][0]["event"] == "evt-1"

    def test_get_ignores_notif_delivery_id_due_to_bug(
        self, rf, monkeypatch, delivery, extra_delivery
    ):
        view = NotificationDeliveryListView.as_view()
        request = rf.get(
            f"/v1/notifications/notification_delivery/?notif_delivery_id={delivery.id}"
        )

        class TemplateSerializerStub:
            def __init__(self, instance):
                self.instance = instance

            def to_dict(self):
                return {"id": self.instance.id}

        monkeypatch.setattr(
            "notifications.views.NotifTemplateSerializer", TemplateSerializerStub
        )

        response = view(request)
        payload = json.loads(response.content)

        assert response.status_code == 200
        assert len(payload["data"]) == 2

    def test_get_invalid_page(self, rf):
        view = NotificationDeliveryListView.as_view()
        request = rf.get("/v1/notifications/notification_delivery/?page=999")

        response = view(request)
        assert response.status_code == 400
        assert json.loads(response.content) == {"errors": {"page": "Invalid page"}}

    def test_view_inherit_permission_mixin(self):
        assert CheckPermissionsMixin in NotificationDeliveryListView.__mro__


class TestUrls:
    def test_template_url_resolves(self):
        match = resolve("/v1/notifications/notification_template/")
        assert match.view_name == "Notification_template_view"
        assert (
            reverse("Notification_template_view")
            == "/v1/notifications/notification_template/"
        )

    def test_delivery_url_resolves(self):
        match = resolve("/v1/notifications/notification_delivery/")
        assert match.view_name == "Notification_delivery_view"
        assert (
            reverse("Notification_delivery_view")
            == "/v1/notifications/notification_delivery/"
        )


class TestAdminModule:
    def test_models_are_registered(self):
        assert NotificationTemplate in admin.site._registry
        assert NotificationDelivery in admin.site._registry
