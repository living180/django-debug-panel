from django.http import HttpResponse
from debug_panel.cache import cache
from django.shortcuts import render
from django.views.decorators.clickjacking import xframe_options_exempt

@xframe_options_exempt
def debug_data(request, timestamp):
    html = cache.get("django-debug-panel:" + timestamp)

    if html is None:
        return render(response, 'debug-data-unavailable.html')

    return HttpResponse(html, content_type="text/html; charset=utf-8")
