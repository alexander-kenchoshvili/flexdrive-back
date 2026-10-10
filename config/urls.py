"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from commerce.accounting_admin import accounting_view

urlpatterns = [
    path('manager-fd/accounting/', admin.site.admin_view(accounting_view), name='accounting-report'),
    path('manager-fd/', admin.site.urls),
    path('api/catalog/', include('catalog.urls')),  
    path('api/commerce/', include('commerce.urls')),
    path('api/pages/', include('pages.urls')),
    path('api/accounts/', include('accounts.urls')),
    path('api/business/', include('business.urls')),


 

]
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)



