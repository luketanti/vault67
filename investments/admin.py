from django.contrib import admin

from .models import InvestmentTransaction, Security, SecurityPrice

admin.site.register(Security)
admin.site.register(SecurityPrice)
admin.site.register(InvestmentTransaction)
