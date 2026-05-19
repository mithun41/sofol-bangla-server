"""
WSGI config for config project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/6.0/howto/deployment/wsgi/
"""

import os
import sys

# 🔥 [CRITICAL] পাইথনঅ্যানিহোয়্যারের ফ্রি প্রক্সি এবং ড্যাঙ্গো সেটিংস সবার আগে পুশ করতে হবে
os.environ["http_proxy"] = "http://proxy.server:3128"
os.environ["https_proxy"] = "http://proxy.server:3128"
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

# 🚀 এবার ড্যাঙ্গোর কোর ডব্লিউএসজিআই মেথড ইমপোর্ট এবং রান হবে
from django.core.wsgi import get_wsgi_application

application = get_wsgi_application()
