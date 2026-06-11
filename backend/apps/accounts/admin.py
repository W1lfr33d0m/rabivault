from django.contrib import admin
from .models import UserProfile


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "organization", "role", "mfa_enabled", "active")
    list_filter = ("role", "mfa_enabled", "active")
    search_fields = ("user__username", "user__email", "organization__name")
