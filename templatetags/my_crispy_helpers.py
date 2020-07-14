from django import forms
from django import template

register = template.Library()


@register.filter
def is_selectmultiple(field) -> bool:
    """helper for crispy forms"""
    return isinstance(field.field.widget, forms.SelectMultiple)


@register.filter
def is_textarea(field) -> bool:
    """helper for crispy forms"""
    return isinstance(field.field.widget, forms.Textarea)
