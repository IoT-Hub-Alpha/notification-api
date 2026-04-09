## Notification API

Simple django API + Django admin for the notification_template and notification_deliveries services.



## Notification template:

### Endpoints:
`...api/v1/notifications/notification_template/`
acceptable methods:
- GET - returns a paginated list of all templates, can be filtered with the `/?notif_template_id=1` query parameter.
- POST - Creates a new template, example body:
```
{
    "name": "My Custom Template",
    "message_template": "AAA",
    "recipients": [
        {
            "type": "sms",
            "phone": "+38000123"
        }
    ],
    "priority": 2,
    "retry_count": 3,
    "is_active": true
}
```
- DELETE - deletes a resource, return 204 with empty json as confirmation, requires `/?notif_template_id=1` query parameter.
- PATCH - partial/full update of a resource, requires `/?notif_template_id=1` query parameter alongside a body. example body:
```
{
    "name": "Updating name",
    "message_template": "AAA",
    "priority": 3,
    "retry_count": 3,
    "is_active": false
}
```

### Permissions:
Admin: `all`

Viewer: `GET` Only

Operator: `GET`/`POST`

## Notification Deliveries:

`...api/v1/notifications/notification_delivery/`

## Endpoints:
- GET - returns a paginated list of all deliveries, can be filtered with the `/?notif_delivery_id=1` query parameter, and/or `/?event_id=1` to filter by event.

## Permissions:
Admin: `all`

Viewer: `GET` Only


