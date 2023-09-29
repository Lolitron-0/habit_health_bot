from django.contrib import admin
from django.db.models.functions import Lower

from .forms import *
from .models import *


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ("nickname", "external_id", "first_name", "sign_up_date")
    search_fields = ("nickname",)
    readonly_fields = ("sign_up_date", "post_list", "tag_list")
    form = UserForm


@admin.register(UserSchedule)
class UserScheduleAdmin(admin.ModelAdmin):
    list_display = ("user", "morning", "noon", "evening")


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ("name", "parent", "level",)
    search_fields = ("name",)
    readonly_fields = ("level",)

    def get_ordering(self, request):
        return [Lower("name"), ]


@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    form = PostForm
    list_display = ("title", "subs_count", "tags_str")
    fields = (
        "title", "score", "description", "technique", "benefits", "relevance", "req_time", "reqs", "created_at",
        "lead_time", "media_id", "video_id", "tags", "order_place")
    readonly_fields = ("created_at",)


@admin.register(BasePost)
class BasePostAdmin(admin.ModelAdmin):
    form = PostForm
    list_display = ("title", "is_bot_habit")
    readonly_fields = ("created_at",)


@admin.register(Sub)
class SubAdmin(admin.ModelAdmin):
    list_display = ("user", "post")


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("get_user", "get_post", "daytime")
    list_display_links = ("get_post",)


@admin.register(DefaultSchedule)
class ScheduleAdmin(admin.ModelAdmin):
    list_display = ("get_post", "daytime")
    fields = ("post", "daytime")
    # form = DefaultScheduleForm


@admin.register(Mailing)
class MailingAdmin(admin.ModelAdmin):
    list_display = ("__str__", "send_time")


@admin.register(LevelReward)
class LevelRewardAdmin(admin.ModelAdmin):
    list_display = ("name", "level_required")


@admin.register(TagReward)
class TagRewardAdmin(admin.ModelAdmin):
    list_display = ("name", "tag", "score_required")


admin.site.register(UserPost)
admin.site.register(Stimulus)
