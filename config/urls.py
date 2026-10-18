from django.contrib import admin
from django.urls import include, path

urlpatterns = [path('admin/', admin.site.urls), path('', include('blog.urls'))]
handler404 = 'blog.views.not_found'
