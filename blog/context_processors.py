from .models import SiteConfig

def site_config(request):
    return {'site': SiteConfig.objects.first() or SiteConfig()}
