"""Accueil de la boutique dans la fenêtre commune."""
from app.views.catalog import CatalogPage
from app.runtime import PageFrame


def main(parent=None, initial_data=None, **options):
    if parent is None:
        from app.runtime import launch
        return launch('accueil')
    page=CatalogPage(home=True, window=PageFrame(parent), initial_data=initial_data)
    return page.window
