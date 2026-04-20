from django.db import migrations


def seed_reglas(apps, schema_editor):
    ReglaCuenta = apps.get_model('api', 'ReglaCuenta')
    reglas = [
        {'empresa': 'hulempak', 'cuenta': '8059', 'prefijos_folio': ['CH', 'MM'],
         'descripcion': 'Cuenta 8059 — facturas CH y MM'},
        {'empresa': 'hulempak', 'cuenta': '3984', 'prefijos_folio': ['PH'],
         'descripcion': 'Cuenta 3984 — facturas PH'},
    ]
    for r in reglas:
        ReglaCuenta.objects.get_or_create(
            empresa=r['empresa'],
            cuenta=r['cuenta'],
            defaults={'prefijos_folio': r['prefijos_folio'], 'descripcion': r['descripcion']},
        )


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0010_regla_cuenta'),
    ]

    operations = [
        migrations.RunPython(seed_reglas, migrations.RunPython.noop),
    ]
