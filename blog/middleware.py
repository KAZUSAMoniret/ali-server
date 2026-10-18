from django.utils.cache import add_never_cache_headers

class PrivateResponseMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        # Withdrawal takes effect on the next request, including cached image URLs.
        if request.path.startswith(('/admin/', '/photos/', '/posts/', '/sitemap.xml')):
            add_never_cache_headers(response)
        return response
