from django.shortcuts import render


def homepage(request):
    return render(request, "homepage/homepage.html")

def support(request):
    return render(request, "homepage/support.html")