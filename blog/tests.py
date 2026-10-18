import tempfile
from io import BytesIO, StringIO
from pathlib import Path
from PIL import Image
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from .images import MAX_BYTES, normalize_image
from .markdown import render_markdown
from .models import Photo, Post, SiteConfig, Tag


def image_upload(fmt='JPEG'):
    stream = BytesIO()
    pic = Image.new('RGB', (80, 40), '#567052')
    exif = Image.Exif()
    exif[274] = 6
    exif[270] = 'private location note'
    pic.save(stream, format=fmt, exif=exif)
    return SimpleUploadedFile('photo.jpg', stream.getvalue(), content_type='image/jpeg')


class BlogTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = get_user_model().objects.create_superuser('writer', password='test-only-password')
        cls.draft = Post.objects.create(title='秘密草稿', body='# 草稿')
        cls.post = Post.objects.create(title='公开手记', slug='public-note', body='## 午后\n\n**你好**', status='published')
        cls.tag = Tag.objects.create(name='日常', slug='daily')
        cls.post.tags.add(cls.tag)
        cls.draft.tags.add(cls.tag)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.media_override = override_settings(MEDIA_ROOT=self.temp.name)
        self.media_override.enable()
        self.addCleanup(self.media_override.disable)

    def photo(self, post=None):
        return Photo.objects.create(post=post or self.draft, file=normalize_image(image_upload()), alt='窗边')

    def test_public_pages_and_draft_exclusion(self):
        for url in ['/', '/archives/', '/tags/daily/', '/sitemap.xml']:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            self.assertNotContains(response, self.draft.title)
            self.assertNotContains(response, self.draft.get_absolute_url())
        self.assertEqual(self.client.get(self.draft.get_absolute_url()).status_code, 404)
        self.assertEqual(self.client.get(self.post.get_absolute_url()).status_code, 200)
        self.assertContains(self.client.get('/about/'), '生活手记')

    def test_publish_edit_withdraw_retains_first_date_and_url(self):
        photo = self.photo()
        self.assertEqual(self.client.get(photo.get_absolute_url()).status_code, 404)
        self.draft.status = 'published'
        self.draft.save()
        first_date, slug = self.draft.published_at, self.draft.slug
        self.assertEqual(self.client.get(self.draft.get_absolute_url()).status_code, 200)
        response = self.client.get(photo.get_absolute_url())
        self.assertEqual(response.status_code, 200)
        self.assertIn('no-store', response['Cache-Control'])
        b''.join(response.streaming_content)
        self.draft.title = '修改标题'
        self.draft.status = 'draft'
        self.draft.save()
        self.assertEqual(self.client.get(self.draft.get_absolute_url()).status_code, 404)
        self.assertEqual(self.client.get(photo.get_absolute_url()).status_code, 404)
        self.draft.status = 'published'
        self.draft.save()
        self.assertEqual(self.draft.published_at, first_date)
        self.assertEqual(self.draft.slug, slug)

    def test_admin_only_preview_and_photo(self):
        photo = self.photo()
        self.client.force_login(self.admin)
        response = self.client.get(photo.get_absolute_url())
        self.assertEqual(response.status_code, 200)
        b''.join(response.streaming_content)
        response = self.client.get(reverse('admin:blog_post_preview', args=[self.draft.pk]))
        self.assertContains(response, 'noindex,nofollow')
        self.assertContains(response, '仅管理员可见')
        self.assertIn('no-store', response['Cache-Control'])

    def test_nonstaff_and_staff_without_permission_denied(self):
        user = get_user_model().objects.create_user('reader', password='test-only-password')
        photo = self.photo()
        for staff in [False, True]:
            user.is_staff = staff
            user.save()
            self.client.force_login(user)
            self.assertEqual(self.client.get(photo.get_absolute_url()).status_code, 404)
            result = self.client.post(reverse('admin:blog_photo_upload', args=[self.draft.pk]), {'image': image_upload()})
            self.assertIn(result.status_code, [302, 403])
        self.assertEqual(Photo.objects.count(), 1)

    def test_anonymous_writes_and_csrf_rejected(self):
        preview_url = reverse('admin:blog_markdown_preview')
        upload_url = reverse('admin:blog_photo_upload', args=[self.draft.pk])
        self.assertEqual(self.client.post(preview_url, {'body': '# hello'}).status_code, 302)
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.admin)
        self.assertEqual(client.post(preview_url, {'body': '# hello'}).status_code, 403)
        self.assertEqual(client.post(upload_url, {'image': image_upload()}).status_code, 403)
        self.assertFalse(Photo.objects.exists())

    def test_upload_and_markdown_preview(self):
        self.client.force_login(self.admin)
        response = self.client.post(reverse('admin:blog_photo_upload', args=[self.draft.pk]),
                                    {'image': image_upload(), 'alt': '一束光'})
        self.assertEqual(response.status_code, 201)
        photo = Photo.objects.get(pk=response.json()['id'])
        self.assertEqual(photo.alt, '一束光')
        self.assertEqual(photo.post, self.draft)
        self.assertTrue(photo.file.name.endswith('.webp'))
        with Image.open(photo.file.path) as normalized:
            self.assertEqual(normalized.size, (40, 80))
            self.assertFalse(normalized.getexif())
        response = self.client.post(reverse('admin:blog_markdown_preview'), {'body': self.post.body})
        self.assertEqual(response.json()['html'], render_markdown(self.post.body))
        self.assertContains(self.client.get(self.post.get_absolute_url()), response.json()['html'])
        self.assertEqual(self.client.get(reverse('admin:blog_photo_upload', args=[self.draft.pk])).status_code, 405)

    def test_invalid_and_oversized_images(self):
        self.client.force_login(self.admin)
        url = reverse('admin:blog_photo_upload', args=[self.draft.pk])
        for data in [b'<svg onload="alert(1)"/>', b'not an image', b'x' * (MAX_BYTES + 1)]:
            response = self.client.post(url, {'image': SimpleUploadedFile('fake.jpg', data, 'image/jpeg')})
            self.assertEqual(response.status_code, 400)
        self.assertFalse(Photo.objects.exists())

    def test_png_and_webp_supported(self):
        for fmt in ['PNG', 'WEBP']:
            normalized = normalize_image(image_upload(fmt))
            self.assertTrue(normalized.name.endswith('.webp'))

    def test_markdown_blocks_active_content(self):
        rendered = render_markdown('<script>alert(1)</script>\n\n[x](javascript:alert%281%29)\n\n![x](data:text/html,evil)\n\n<img src=x onerror=alert(1)>')
        self.assertNotIn('<script>', rendered)
        self.assertNotIn('<img src=x', rendered)
        self.assertNotIn('href="javascript:', rendered)
        self.assertNotIn('src="data:', rendered)
        self.assertIn('&lt;script&gt;', rendered)

    def test_cross_post_cover_rejected(self):
        photo = self.photo()
        self.post.cover = photo
        with self.assertRaises(ValidationError):
            self.post.full_clean()

    @override_settings(USE_X_ACCEL=True)
    def test_nginx_media_protection(self):
        photo = self.photo(self.post)
        response = self.client.get(photo.get_absolute_url())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['X-Accel-Redirect'], '/_protected_media/' + photo.file.name)
        self.assertEqual(response.content, b'')
        self.assertEqual(self.client.get('/media/' + photo.file.name).status_code, 404)
        self.assertEqual(self.client.get('/_protected_media/' + photo.file.name).status_code, 404)

    def test_missing_image_is_404(self):
        photo = self.photo(self.post)
        Path(photo.file.path).unlink()
        self.assertEqual(self.client.get(photo.get_absolute_url()).status_code, 404)

    @override_settings(DEBUG=False)
    def test_custom_404_and_empty_pages(self):
        self.assertContains(self.client.get('/missing/'), '这一页，暂时走丢了。', status_code=404)
        Post.objects.all().delete()
        self.assertContains(self.client.get('/'), '第一篇手记还在酝酿')
        self.assertContains(self.client.get('/archives/'), '等待落笔')

    def test_pagination(self):
        for i in range(10):
            Post.objects.create(title=f'文章 {i}', status='published')
        response = self.client.get('/?page=2')
        self.assertEqual(len(response.context['page_obj']), 3)
        self.assertEqual(self.client.get('/?page=invalid').status_code, 200)

    def test_sitemap_uses_configured_origin(self):
        with override_settings(SITE_URL='https://example.com'):
            response = self.client.get('/sitemap.xml')
        self.assertContains(response, 'https://example.com/posts/public-note/')
        self.assertNotContains(response, self.draft.slug)

    def test_admin_editor_and_cover_choices(self):
        own, other = self.photo(), self.photo(self.post)
        self.client.force_login(self.admin)
        response = self.client.get(reverse('admin:blog_post_change', args=[self.draft.pk]))
        self.assertContains(response, '预览当前 Markdown')
        self.assertContains(response, '上传并插入正文')
        form = response.context['adminform'].form
        self.assertEqual(list(form.fields['cover'].queryset), [own])

    def test_site_config_singleton(self):
        SiteConfig(name='A').save()
        SiteConfig(name='B').save()
        self.assertEqual(SiteConfig.objects.count(), 1)
        self.assertEqual(SiteConfig.objects.get().name, 'B')

    def test_demo_idempotent_and_disabled_in_production(self):
        call_command('seed_demo', stdout=StringIO())
        count = Post.objects.count()
        call_command('seed_demo', stdout=StringIO())
        self.assertEqual(Post.objects.count(), count)
        from django.core.management.base import CommandError
        with override_settings(PRODUCTION=True), self.assertRaises(CommandError):
            call_command('seed_demo')


    def test_admin_form_publish_and_withdraw(self):
        self.client.force_login(self.admin)
        url = reverse('admin:blog_post_add')
        data = {'title': '后台新增', 'slug': 'admin-created', 'body': '# 新文章', 'status': 'draft',
                'summary': '', 'cover': '', 'photos-TOTAL_FORMS': '0', 'photos-INITIAL_FORMS': '0',
                'photos-MIN_NUM_FORMS': '0', 'photos-MAX_NUM_FORMS': '1000', '_save': '保存'}
        self.assertEqual(self.client.post(url, data).status_code, 302)
        post = Post.objects.get(slug='admin-created')
        self.assertEqual(post.status, 'draft')
        change = reverse('admin:blog_post_change', args=[post.pk])
        data['status'] = 'published'
        self.assertEqual(self.client.post(change, data).status_code, 302)
        self.assertEqual(Client().get(post.get_absolute_url()).status_code, 200)
        data['status'] = 'draft'
        self.assertEqual(self.client.post(change, data).status_code, 302)
        self.assertEqual(Client().get(post.get_absolute_url()).status_code, 404)
