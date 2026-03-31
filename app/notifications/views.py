import json
import logging
from functools import wraps
from uuid import UUID
from django.shortcuts import get_object_or_404, render
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.db import transaction
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from .services.exceptions import ApiValidationError, BadRequestError, NotFoundError
from .services.serializer import NotifTemplateSerializer, template_update
from .services.data_type import AuthenticatedHttpRequest
from .models import NotificationTemplate, NotificationDelivery

logger = logging.getLogger(__name__)

def _json_body(request: HttpRequest) -> dict:
    try:
        if not request.body:
            return {}
        return json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError:
        raise BadRequestError("Invalid JSON body.")


def _parse_uuid(value: str) -> UUID:
    if isinstance(value, UUID):
        return value
    try:
        return UUID(str(value))
    except (ValueError, TypeError):
        raise BadRequestError("Invalid UUID format.")


def handle_api_errors(view_func):
    @wraps(view_func)
    def wrapper(*args, **kwargs):
        try:
            return view_func(*args, **kwargs)
        except ApiValidationError as e:
            logger.error("ApiValidationError", extra={"errors": e.errors, "status": e.status_code})
            return JsonResponse({"errors": e.errors}, status=e.status_code)
        except BadRequestError as e:
            logger.error("BadRequestError", extra={"errors": e.message, "status": e.status_code})
            return JsonResponse({"error": e.message}, status=e.status_code)
        except NotFoundError as e:
            logger.error("NotFoundError", extra={"errors": e.message, "status": e.status_code})
            return JsonResponse({"error": e.message}, status=e.status_code)
        except ValueError as e:
            logger.error("ValueError", extra={"errors": str(e), "status": 400})
            return JsonResponse({"error": str(e)}, status=400)

    return wrapper

@method_decorator(csrf_exempt, name="dispatch")
class NotificationTemplateListView(View):
    default_page_size = 10

    def get(self, request: AuthenticatedHttpRequest) -> JsonResponse:
        if not request.jwt_payload:
            return JsonResponse({"error": "Authentication required"}, status=401)

        user_id = request.jwt_payload.get("user_id")
        premissions = request.jwt_payload.get("permissions")
        
        print(f"user: {user_id}, perms: {premissions}")
        
        qs = NotificationTemplate.objects.all()

        notif_template_id = request.GET.get("notif_template_id")
        if notif_template_id:
            qs = qs.filter(id=notif_template_id)

        page_number = request.GET.get("page", 1)
        page_size = int(request.GET.get("page_size", self.default_page_size))
        paginator = Paginator(qs, page_size)

        try:
            page_obj = paginator.page(page_number)
        except (PageNotAnInteger, EmptyPage):
            return JsonResponse({"errors": {"page": "Invalid page"}}, status=400)

        data = [NotifTemplateSerializer(instance=obj).to_dict() for obj in page_obj.object_list]

        return JsonResponse(
            {
                "data": data,
                "pagination": {
                    "page": page_obj.number,
                    "page_size": page_size,
                    "total": paginator.count,
                    "total_pages": paginator.num_pages,
                    "next_page": (
                        page_obj.next_page_number() if page_obj.has_next() else None
                    ),
                    "prev_page": (
                        page_obj.previous_page_number()
                        if page_obj.has_previous()
                        else None
                    ),
                },
            },
            status=200,
        )

    @handle_api_errors
    def post(self, request: HttpRequest) -> JsonResponse | None:
            data = _json_body(request)
            instance = NotificationTemplate.create(data)
            return JsonResponse(NotifTemplateSerializer(instance=instance).to_dict())
        
    
    @handle_api_errors
    def delete(self, request: HttpRequest) -> JsonResponse:
        notif_template_id = request.GET.get("notif_template_id")
        if not notif_template_id:
            return JsonResponse({"error": "No notif_template_id provided"}, status=400)
        instance = NotificationTemplate.objects.filter(id=notif_template_id).first()
        instance = get_object_or_404(NotificationTemplate, id=notif_template_id)
        
        instance.delete()
        
        return JsonResponse({}, status=204)
    
    @handle_api_errors
    def patch(self, request: HttpRequest) -> JsonResponse:
        data = _json_body(request)
        notif_template_id = request.GET.get("notif_template_id")
        
        if not notif_template_id:
            return JsonResponse({"error": "No notif_template_id provided"}, status=400)
        
        instance = get_object_or_404(NotificationTemplate, id=notif_template_id)
        updated_instance = template_update(instance, data)
        
        return JsonResponse(NotifTemplateSerializer(instance=updated_instance).to_dict())
        
        
@method_decorator(csrf_exempt, name="dispatch")
class NotificationDeliveryListView(View):
    default_page_size = 10

    def get(self, request: HttpRequest) -> JsonResponse:
        
        qs = NotificationDelivery.objects.all()

        notif_delivery_id = request.GET.get("notif_template_id")
        if notif_delivery_id:
            qs = qs.filter(id=notif_delivery_id)

        page_number = request.GET.get("page", 1)
        page_size = int(request.GET.get("page_size", self.default_page_size))
        paginator = Paginator(qs, page_size)

        try:
            page_obj = paginator.page(page_number)
        except (PageNotAnInteger, EmptyPage):
            return JsonResponse({"errors": {"page": "Invalid page"}}, status=400)

        data = [NotifTemplateSerializer(instance=obj).to_dict() for obj in page_obj.object_list]

        return JsonResponse(
            {
                "data": data,
                "pagination": {
                    "page": page_obj.number,
                    "page_size": page_size,
                    "total": paginator.count,
                    "total_pages": paginator.num_pages,
                    "next_page": (
                        page_obj.next_page_number() if page_obj.has_next() else None
                    ),
                    "prev_page": (
                        page_obj.previous_page_number()
                        if page_obj.has_previous()
                        else None
                    ),
                },
            },
            status=200,
        )