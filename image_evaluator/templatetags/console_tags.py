import json

from django import template

register = template.Library()


@register.filter
def pretty_json(value) -> str:
    if value is None:
        return ""
    return json.dumps(value, indent=2, default=str, ensure_ascii=False)


@register.filter
def short_id(value) -> str:
    text = str(value)
    return text[:8] if len(text) > 8 else text


@register.filter
def get_item(mapping, key):
    if mapping is None:
        return ""
    return mapping.get(key, "")
