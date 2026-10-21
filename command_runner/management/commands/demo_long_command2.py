import time

from ._base import ReporterCommand

from stroykerbox.apps.catalog.models import Product


class Command(ReporterCommand):
    help = "Демонстрационная долгая команда, показывающая прогресс и stop."

    def add_arguments(self, parser):
        parser.add_argument("--steps", type=int, default=20)

    def handle(self, *args, **options):
        steps = max(1, options["steps"])
        qs = Product.objects.all()[:steps]
        self.stdout.write("Печатает товары номер два")
        for i in range(steps):
            self.reporter.check_stop()
            # self.stdout.write(f"Шаг {i + 1} из {steps}")
            self.stdout.write(f"Товар: {qs[i]}")
            self.reporter.progress(int((i + 1) / steps * 100), f"Шаг {i + 1}/{steps}")
            time.sleep(0.5)
        self.stdout.write("Готово")
