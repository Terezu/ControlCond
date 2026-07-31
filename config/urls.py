"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

from .views import health_check

urlpatterns = [
    path("healthz/", health_check, name="healthz"),
    path(
        "conta/entrar/",
        auth_views.LoginView.as_view(template_name="registration/login.html"),
        name="login",
    ),
    path(
        "conta/sair/",
        auth_views.LogoutView.as_view(),
        name="logout",
    ),
    path(
        "conta/senha/alterar/",
        auth_views.PasswordChangeView.as_view(
            template_name="registration/password_change_form.html",
            success_url="/usuarios/perfil/",
        ),
        name="password_change",
    ),
    path(
        "conta/senha/recuperar/",
        auth_views.PasswordResetView.as_view(
            template_name="registration/password_reset_form.html",
            email_template_name="registration/password_reset_email.txt",
            success_url="/conta/senha/recuperar/enviado/",
        ),
        name="password_reset",
    ),
    path(
        "conta/senha/recuperar/enviado/",
        auth_views.PasswordResetDoneView.as_view(
            template_name="registration/password_reset_done.html"
        ),
        name="password_reset_done",
    ),
    path(
        "conta/senha/redefinir/<uidb64>/<token>/",
        auth_views.PasswordResetConfirmView.as_view(
            template_name="registration/password_reset_confirm.html",
            success_url="/conta/senha/redefinir/concluida/",
        ),
        name="password_reset_confirm",
    ),
    path(
        "conta/senha/redefinir/concluida/",
        auth_views.PasswordResetCompleteView.as_view(
            template_name="registration/password_reset_complete.html"
        ),
        name="password_reset_complete",
    ),
    path("", include("dashboard.urls")),
    path('admin/', admin.site.urls),
    path('apartamentos/', include('apartamentos.urls')),
    path('leituras/', include('leituras.urls')),
    path('faturas/', include('faturas.urls')),
    path('pessoas/', include('pessoas.urls')),
    path('contratos/', include('contratos.urls')),
    path('usuarios/', include('usuarios.urls')),
    path('configuracoes/', include('configuracoes.urls')),
    path('condominios/', include('condominios.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
