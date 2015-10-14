"""
Debug Panel middleware
"""
import threading
import time

from django.core.urlresolvers import reverse, resolve, Resolver404
from django.conf import settings
from debug_panel.cache import cache
import debug_toolbar.middleware
import debug_toolbar.views

# the urls patterns that concern only the debug_panel application
import debug_panel.urls

def show_toolbar(request):
    """
    Default function to determine whether to show the toolbar on a given page.
    """
    if request.META.get('REMOTE_ADDR', None) not in settings.INTERNAL_IPS:
        return False

    # don't show the toolbar for django-debug-toolbar URLs
    try:
        match = resolve(request.path)
    except Resolver404:
        pass
    else:
        if match.func.__module__ == debug_toolbar.views:
            return False

    return bool(settings.DEBUG)


debug_toolbar.middleware.show_toolbar = show_toolbar


class DebugPanelMiddleware(debug_toolbar.middleware.DebugToolbarMiddleware):
    """
    Middleware to set up Debug Panel on incoming request and render toolbar
    on outgoing response.
    """

    def process_request(self, request):
        """
        Try to match the request with an URL from debug_panel application.

        If it matches, that means we are serving a view from debug_panel,
        and we can skip the debug_toolbar middleware.

        Otherwise we fallback to the default debug_toolbar middleware.
        """

        try:
            res = resolve(request.path, urlconf=debug_panel.urls)
        except Resolver404:
            return super(DebugPanelMiddleware, self).process_request(request)

        return res.func(request, *res.args, **res.kwargs)


    def process_response(self, request, response):
        """
        Store the DebugToolbarMiddleware rendered toolbar into a cache store.

        The data stored in the cache are then reachable from an URL that is appened
        to the HTTP response header under the 'X-debug-data-url' key.
        """
        toolbar = self.__class__.debug_toolbars.get(threading.current_thread().ident, None)

        response = super(DebugPanelMiddleware, self).process_response(request, response)

        if toolbar:
            # for django-debug-toolbar >= 1.4
            for panel in reversed(toolbar.enabled_panels):
                if hasattr(panel, 'generate_stats'):
                    panel.generate_stats(request, response)

            timestamp = "%f" % time.time()
            cache_key = "django-debug-panel:" + timestamp
            cache.set(cache_key, toolbar.render_toolbar())

            response['X-debug-data-url'] = request.build_absolute_uri(
                reverse('debug_data', urlconf=debug_panel.urls, kwargs={'timestamp': timestamp}))

        return response
