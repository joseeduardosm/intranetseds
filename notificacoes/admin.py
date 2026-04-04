from django.contrib import admin

from .models import DesktopAPIToken, NotificacaoUsuario


@admin.register(NotificacaoUsuario)
class NotificacaoUsuarioAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "source_app", "event_type", "title", "created_at", "read_at", "displayed_at")
    list_filter = ("source_app", "event_type", "read_at", "displayed_at")
    search_fields = ("user__username", "user__email", "title", "body_short", "target_url", "dedupe_key")


@admin.register(DesktopAPIToken)
class DesktopAPITokenAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "token_prefix", "created_at", "last_used_at", "expires_at", "revoked_at")
    list_filter = ("revoked_at",)
    search_fields = ("user__username", "user__email", "token_prefix")

