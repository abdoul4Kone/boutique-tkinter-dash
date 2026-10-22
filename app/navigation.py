"""Routes du lanceur : aucun écran ne dépend du nom de fichier d'un autre."""

import sys

from app.config import ROOT_DIR

ROUTES = {
    "accueil": "app.views.home",
    "catalogue": "app.views.catalog",
    "produit": "app.views.product",
    "connexion": "app.views.login",
    "inscription": "app.views.register",
    "panier": "app.views.cart",
    "commande": "app.views.checkout",
    "mes-commandes": "app.views.orders",
    "confirmation": "app.views.orders",
    "administration": "app.admin.login",
    "tableau-de-bord": "app.admin.dashboard",
    "generer-clients": "app.scripts.seed_users",
    "generer-commandes": "app.scripts.seed_orders",
}
PUBLIC_RETURNS = {"accueil", "catalogue", "panier", "mes-commandes"}


def split_target(target):
    parts = target.split(":")
    if len(parts) == 2 and parts[0] in ("produit", "confirmation") and parts[1].isascii() and parts[1].isdigit() and int(parts[1]) > 0:
        return parts[0], int(parts[1])
    if len(parts) == 1 and target in ROUTES and target not in ("produit", "confirmation"):
        return target, None
    raise ValueError(f"Destination inconnue : {target}")


def normalize_return(target):
    try:
        route, _ = split_target(target)
    except (ValueError, AttributeError):
        return "accueil"
    return target if route in PUBLIC_RETURNS | {"produit", "confirmation"} else "accueil"


def command_for(target, return_to=None):
    route, product_id = split_target(target)
    command = [sys.executable, str(ROOT_DIR / "main.py"), route]
    if product_id is not None:
        command += ["--id", str(product_id)]
    if return_to is not None:
        command += ["--retour", normalize_return(return_to)]
    return command


def open_page(target, window=None, return_to=None, receipt=None):
    from app.runtime import Application, launch
    controller = getattr(window, '_app_controller', None)
    if isinstance(controller, Application):
        return controller.navigate(target, return_to=return_to, receipt=receipt)
    return launch(target, return_to=return_to)
