from django import forms

import datetime as dt

from .models import *

HOUR_CHOICES = [(dt.time(hour=x), '{:02d}:00'.format(x)) for x in range(0, 24)]


class DefaultScheduleForm(forms.ModelForm):
    class Meta:
        model = DefaultSchedule
        fields = '__all__'
        widgets = {'time': forms.Select(choices=HOUR_CHOICES)}


class UserForm(forms.ModelForm):
    model = User
    fields = '__all__'


class PostForm(forms.ModelForm):

    class Meta:
        model = Post
        fields = '__all__'
        widgets = {"media_id": forms.TextInput, "video_id": forms.TextInput}

