from django.apps import AppConfig


class DrugsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'drugs'
    verbose_name = '식약처 3대 OpenAPI 통합 의약품 서비스'
