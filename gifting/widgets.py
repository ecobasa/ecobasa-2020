from django import forms


class LocationWidget(forms.TextInput):
    template_name = "widgets/location_widget.html"
