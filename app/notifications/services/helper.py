def construct_paginated_response(data, page_obj, page_size, paginator):
    return {
        "data": data,
        "pagination": {
            "page": page_obj.number,
            "page_size": page_size,
            "total": paginator.count,
            "total_pages": paginator.num_pages,
            "next_page": (page_obj.next_page_number() if page_obj.has_next() else None),
            "prev_page": (
                page_obj.previous_page_number() if page_obj.has_previous() else None
            ),
        },
    }
