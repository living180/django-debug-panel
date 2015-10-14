"""
Debug Panel middleware
"""
import threading
import time

from django.core.urlresolvers import reverse, resolve, Resolver404
from django.conf import settings

import debug_toolbar.views
from debug_toolbar.middleware import DebugToolbarMiddleware

import debug_panel.urls
from debug_panel.cache import cache


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


class DebugPanelMiddleware(DebugToolbarMiddleware):
    """
    Middleware to check for and handle debug panel URLs in incoming requests,
    and to render the toolbar for outgoing responses.
    """

    def process_request(self, request):
        """
        Try to match the request with an URL from debug_panel application.

        If it matches, that means we are serving a view from debug_panel,
        so call that view directly, bypassing the DebugToolbarMiddleware
        functionality.

        Otherwise fall back to the normal DebugToolbarMiddleware
        implementation.
        """

        try:
            match = resolve(request.path, urlconf=debug_panel.urls)
        except Resolver404:
            return super(DebugPanelMiddleware, self).process_request(request)
        else:
            return match.func(request, *match.args, **match.kwargs)

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
