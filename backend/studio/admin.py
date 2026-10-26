from .models import GlossaryEntry, Job, Page, Project, TextBlock

try:
    from .models import GlobalSetting
except ImportError:  # pragma: no cover
    GlobalSetting = None

import django.contrib.admin as admin_mod

site = admin_mod.site
site.register(Project)
site.register(Page)
site.register(TextBlock)
site.register(Job)
site.register(GlossaryEntry)
if GlobalSetting:
    site.register(GlobalSetting)
