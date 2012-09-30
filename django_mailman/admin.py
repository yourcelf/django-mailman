from django.contrib import admin

from django_mailman.models import List, ListMessage

admin.site.register(List)
class ListMessageAdmin(admin.ModelAdmin):
    list_display = ('date', 'message_id', 'thread_order_denormalized', 'thread_depth_denormalized', 'in_reply_to')
admin.site.register(ListMessage, ListMessageAdmin)
