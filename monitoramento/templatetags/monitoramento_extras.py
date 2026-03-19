from django import template


register = template.Library()


@register.filter
def get_item(value, key):
    if value is None:
        return ""
    if hasattr(value, "get"):
        return value.get(key, "")
    try:
        return value[key]
    except Exception:
        return ""


@register.filter
def concat(value, arg):
    return f"{value}{arg}"
