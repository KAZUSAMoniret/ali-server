import uuid
from django.core.exceptions import ValidationError
from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify


class Tag(models.Model):
    name = models.CharField('名称', max_length=40, unique=True)
    slug = models.SlugField('网址标识', max_length=80, unique=True, allow_unicode=True)

    class Meta:
        verbose_name = '标签'
        verbose_name_plural = '标签'
        ordering = ['name']

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse('tag', args=[self.slug])


class PostQuerySet(models.QuerySet):
    def published(self):
        return self.filter(status='published', published_at__isnull=False)


class Post(models.Model):
    class Status(models.TextChoices):
        DRAFT = 'draft', '草稿'
        PUBLISHED = 'published', '已发布'

    title = models.CharField('标题', max_length=200)
    slug = models.SlugField('网址标识', max_length=220, unique=True, blank=True, allow_unicode=True,
                            help_text='首次保存自动生成，后续修改标题不会改变链接。')
    summary = models.CharField('摘要', max_length=300, blank=True)
    body = models.TextField('Markdown 正文', blank=True)
    cover = models.ForeignKey('Photo', verbose_name='封面', null=True, blank=True, on_delete=models.SET_NULL,
                              related_name='cover_for')
    tags = models.ManyToManyField(Tag, verbose_name='标签', blank=True)
    status = models.CharField('状态', choices=Status.choices, default=Status.DRAFT, max_length=12, db_index=True)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)
    published_at = models.DateTimeField('首次发布时间', null=True, blank=True, editable=False)
    objects = PostQuerySet.as_manager()

    class Meta:
        ordering = ['-published_at', '-created_at']
        verbose_name = '文章'
        verbose_name_plural = '文章'

    def __str__(self):
        return self.title

    def clean(self):
        if self.cover_id and self.cover.post_id != self.pk:
            raise ValidationError({'cover': '封面必须是这篇文章上传的图片。'})

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = f'{slugify(self.title, allow_unicode=True)[:180] or "post"}-{uuid.uuid4().hex[:8]}'
        if self.status == self.Status.PUBLISHED and not self.published_at:
            self.published_at = timezone.now()
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse('post', args=[self.slug])


class Photo(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name='photos')
    file = models.FileField(upload_to='photos/%Y/%m/', max_length=250)
    alt = models.CharField('图片说明', max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']
        verbose_name = '图片'
        verbose_name_plural = '图片'

    def __str__(self):
        return self.alt or str(self.pk)

    def get_absolute_url(self):
        return reverse('photo', args=[self.pk])


class SiteConfig(models.Model):
    name = models.CharField('博客名称', max_length=80, default='日子慢慢')
    description = models.CharField('简介', max_length=250, default='把平凡日子里的微光，一点一点收集起来。')
    about = models.TextField('关于我（Markdown）', default='你好，欢迎来到我的生活手记。\n\n在这里，记录走过的路、读过的书，以及值得记住的小事。')
    icp_number = models.CharField('备案号', max_length=80, blank=True)

    class Meta:
        verbose_name = '站点设置'
        verbose_name_plural = '站点设置'

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    def __str__(self):
        return '博客信息'
