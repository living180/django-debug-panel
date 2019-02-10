"""
Debug Panel middleware
"""
import functools
import threading
import time

from django.core.urlresolvers import reverse, resolve, Resolver404
from django.conf import settings

from debug_toolbar.middleware import DebugToolbarMiddleware
from debug_toolbar.panels import Panel
from debug_toolbar.toolbar import DebugToolbar

import debug_panel.urls
from debug_panel.cache import cache


# Check for the Panel.generate_stats() method, added with django-debug-toolbar
# 1.4
_has_generate_stats = hasattr(Panel, 'generate_stats')


def show_toolbar(request):
    """
    Default function to determine whether to show the toolbar on a given page.
    """
    import debug_toolbar.views

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

    # don't show the toolbar for AJAX requests, unless the
    # X-Django-Debug-Toolbar header is present
    if request.is_ajax() and 'HTTP_X_DJANGO_DEBUG_PANEL' not in request.META:
        return False

    return bool(settings.DEBUG)


class _SentinelPanel(Panel):
    def __init__(self, toolbar):
        super(_SentinelPanel, self).__init__(toolbar)
        self.stats_generated = False

    def generate_stats(self, request, response):
        self.stats_generated = True


# Monkey-patch the DebugToolbar.render_toolbar() method to cache the rendered
# HTML, so that if the render_toolbar() method was already called by the
# DebugToolMiddleware.process_response() method, it does not get rendered again
# when render_toolbar() is called from our
# DebugPanelMiddleware.process_response() method.
_render_toolbar = DebugToolbar.render_toolbar
@functools.wraps(_render_toolbar)
def _patched_render_toolbar(self):
    rendered_output = getattr(self, '_rendered_output', None)
    if rendered_output is None:
        # When used with django-debug-toolbar>=1.4 the
        # DebugPanelMiddleware.process_response() method will have inserted a
        # _SentinelPanel into the toolbar's enabled_panels list to detect
        # whether the panels' generate_stats() methods are called.  However, we
        # need to remove that fake panel from the enabled_panels list before
        # the the real DebugToolbar.render_toolbar() method is called.
        if _has_generate_stats:
            for panel in self.panels:
                if isinstance(panel, _SentinelPanel):
                    self._panels.pop(panel.panel_id)
                    break
        rendered_output = _render_toolbar(self)
        self._rendered_output = rendered_output
    return rendered_output
DebugToolbar.render_toolbar = _patched_render_toolbar


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
        In addition to rendering the toolbar inside the response HTML, store it
        in the Django cache.

        The cached toolbar is then reachable from an URL that is appended to
        the HTTP response header under the 'X-debug-data-url' key.
        """

        # DebugToolbarMiddleware.process_response() removes the toolbar from
        # self.debug_toolbars, so get a reference to it before calling that
        # method.
        toolbar = self.debug_toolbars.get(threading.current_thread().ident)
        if _has_generate_stats and toolbar:
            # When using django-debug-toolbar>=1.4, insert a _SentinelPanel
            # into the toolbar to detect whether or not the generate_stats()
            # method is called.  The DebugToolbar.render_toolbar() method will
            # have been monkey-patched to remove this panel immediately before
            # the toolbar is rendered.
            sentinel_panel = _SentinelPanel(toolbar)
            toolbar._panels[sentinel_panel.panel_id] = sentinel_panel

        response = super(DebugPanelMiddleware, self).process_response(request, response)

        if toolbar:
            # In django-debug-toolbar>=1.4, the panels' generate_stats()
            # methods are not called if the debug toolbar is not going to be
            # inserted into the response body (e.g. for an AJAX response).
            # However, the generate_stats() calls must be made before calling
            # the toolbar's render_toolbar() method, so do that here if it was
            # not done previously.
            if _has_generate_stats and not sentinel_panel.stats_generated:
                for panel in reversed(toolbar.enabled_panels):
                    panel.generate_stats(request, response)

            timestamp = "%f" % time.time()
            cache_key = "django-debug-panel:" + timestamp
            cache.set(cache_key, toolbar.render_toolbar())

            response['X-debug-data-url'] = request.build_absolute_uri(
                reverse('debug_data', urlconf=debug_panel.urls, kwargs={'timestamp': timestamp}))

        return response
