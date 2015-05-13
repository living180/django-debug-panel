from django.core.cache.backends.base import InvalidCacheBackendError


try:
    from django.core.cache import caches
except ImportError:
    from django.core.cache import get_cache
else:
    def get_cache(alias):
        return caches[alias]

try:
    cache = get_cache('debug-panel')
except InvalidCacheBackendError:
    from django.core.cache import cache
