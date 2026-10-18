from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'), path('posts/<str:slug>/', views.post_detail, name='post'),
    path('archives/', views.archives, name='archives'), path('tags/<str:slug>/', views.tag, name='tag'),
    path('about/', views.about, name='about'), path('photos/<uuid:pk>/', views.photo, name='photo'),
    path('sitemap.xml', views.sitemap, name='sitemap'),
]
