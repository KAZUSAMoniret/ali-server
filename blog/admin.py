import re
from django.contrib import admin
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import path, reverse
from django.utils.html import format_html
from django.views.decorators.http import require_POST
from .images import normalize_image
from .markdown import render_markdown
from .models import Photo, Post, SiteConfig, Tag


class PhotoInline(admin.TabularInline):
    model = Photo
    fields = ('thumbnail', 'alt', 'markdown_link')
    readonly_fields = ('thumbnail', 'markdown_link')
    extra = 0
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False

    @admin.display(description='预览')
    def thumbnail(self, obj):
        return format_html('<img src="{}" alt="{}" style="max-width:120px;max-height:80px">', obj.get_absolute_url(), obj.alt)

    @admin.display(description='Markdown 地址')
    def markdown_link(self, obj):
        alt = re.sub(r'([\\\[\]])', r'\\\1', obj.alt).replace('\n', ' ').replace('\r', ' ')
        return format_html('<code>![{}]({})</code>', alt, obj.get_absolute_url())


@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    list_display = ('title', 'status', 'published_at', 'updated_at')
    list_filter = ('status', 'tags')
    search_fields = ('title', 'body')
    readonly_fields = ('created_at', 'updated_at', 'published_at')
    filter_horizontal = ('tags',)
    inlines = [PhotoInline]
    change_form_template = 'admin/blog/post/change_form.html'
    fields = ('title', 'slug', 'summary', 'body', 'cover', 'tags', 'status',
              'published_at', 'created_at', 'updated_at')
    actions = None

    def get_urls(self):
        return [
            path('markdown-preview/', self.admin_site.admin_view(require_POST(self.markdown_preview)), name='blog_markdown_preview'),
            path('<int:post_id>/upload/', self.admin_site.admin_view(require_POST(self.upload_photo)), name='blog_photo_upload'),
            path('<int:post_id>/preview/', self.admin_site.admin_view(self.preview_post), name='blog_post_preview'),
        ] + super().get_urls()

    def markdown_preview(self, request):
        if not self.has_change_permission(request):
            raise PermissionDenied
        return JsonResponse({'html': render_markdown(request.POST.get('body', ''))})

    def upload_photo(self, request, post_id):
        post = get_object_or_404(Post, pk=post_id)
        if not self.has_change_permission(request, post):
            raise PermissionDenied
        upload = request.FILES.get('image')
        if not upload:
            return JsonResponse({'error': '请选择图片。'}, status=400)
        try:
            normalized = normalize_image(upload)
        except ValidationError as exc:
            return JsonResponse({'error': '；'.join(exc.messages)}, status=400)
        photo = Photo(post=post, alt=request.POST.get('alt', '')[:200])
        photo.file.save(normalized.name, normalized, save=False)
        try:
            photo.save()
        except Exception:
            photo.file.delete(save=False)
            raise
        return JsonResponse({'id': str(photo.pk), 'url': photo.get_absolute_url(), 'alt': photo.alt}, status=201)

    def preview_post(self, request, post_id):
        post = get_object_or_404(Post, pk=post_id)
        if not self.has_view_permission(request, post):
            raise PermissionDenied
        return render(request, 'blog/post.html', {
            'post': post, 'body_html': render_markdown(post.body), 'is_preview': True,
        })

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        if 'cover' in form.base_fields:
            form.base_fields['cover'].queryset = Photo.objects.filter(post=obj) if obj else Photo.objects.none()
        return form

    def changeform_view(self, request, object_id=None, form_url='', extra_context=None):
        context = dict(extra_context or {})
        context['markdown_preview_url'] = reverse('admin:blog_markdown_preview')
        if object_id:
            context['photo_upload_url'] = reverse('admin:blog_photo_upload', args=[object_id])
            context['post_preview_url'] = reverse('admin:blog_post_preview', args=[object_id])
        return super().changeform_view(request, object_id, form_url, context)


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    prepopulated_fields = {'slug': ('name',)}
    search_fields = ('name',)


@admin.register(SiteConfig)
class SiteConfigAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return not SiteConfig.objects.exists() and super().has_add_permission(request)

    def has_delete_permission(self, request, obj=None):
        return False


admin.site.site_header = '日子慢慢 · 写作后台'
admin.site.site_title = '博客管理'
admin.site.index_title = '今天，有什么值得记下来？'
