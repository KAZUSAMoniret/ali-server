from urllib.parse import quote
from django.conf import settings
from django.core.paginator import Paginator
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from .markdown import render_markdown
from .models import Photo, Post, SiteConfig, Tag

def published():
    return Post.objects.published().select_related('cover').prefetch_related('tags')

def home(request):
    return render(request, 'blog/home.html', {'page_obj': Paginator(published(), 8).get_page(request.GET.get('page'))})

def post_detail(request, slug):
    post = get_object_or_404(published(), slug=slug)
    return render(request, 'blog/post.html', {'post': post, 'body_html': render_markdown(post.body)})

def archives(request):
    return render(request, 'blog/archives.html', {'posts': published()})

def tag(request, slug):
    selected = get_object_or_404(Tag, slug=slug)
    return render(request, 'blog/home.html', {'selected_tag': selected,
                  'page_obj': Paginator(published().filter(tags=selected), 8).get_page(request.GET.get('page'))})

def about(request):
    site = SiteConfig.objects.first() or SiteConfig()
    return render(request, 'blog/about.html', {'body_html': render_markdown(site.about)})

def photo(request, pk):
    item = get_object_or_404(Photo.objects.select_related('post'), pk=pk)
    if item.post.status != Post.Status.PUBLISHED:
        if not (request.user.is_active and request.user.is_staff and request.user.has_perm('blog.view_post')):
            raise Http404
    if not item.file.storage.exists(item.file.name):
        raise Http404
    if settings.USE_X_ACCEL:
        response = HttpResponse(content_type='image/webp')
        response['X-Accel-Redirect'] = '/_protected_media/' + quote(item.file.name, safe='/')
    else:
        response = FileResponse(item.file.open('rb'), content_type='image/webp')
    response['Content-Disposition'] = 'inline'
    return response

def sitemap(request):
    urls = [{'loc': settings.SITE_URL + reverse(name)} for name in ['home', 'archives', 'about']]
    urls += [{'loc': settings.SITE_URL + post.get_absolute_url(), 'lastmod': post.updated_at} for post in published()]
    return render(request, 'blog/sitemap.xml', {'urls': urls}, content_type='application/xml')

def not_found(request, exception):
    return render(request, '404.html', status=404)
