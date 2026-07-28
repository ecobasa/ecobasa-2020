from django import forms


class LocationWidget(forms.TextInput):
    template_name = "maps/location_widget.html"
