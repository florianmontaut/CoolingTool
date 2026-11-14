# ressources/app_settings.py
"""
Schéma des options de l'application (voir qtsocle.options_panel) : un onglet par groupe
de premier niveau, « key » est le nom de l'option dans les réglages.
"""


def schema() -> dict:
    return {
        "Général": {
            "type": "group",
            "children": {
                # vide : la librairie livrée avec l'application. Sinon un dossier (par
                # exemple partagé) contenant dissipateurs/, sources/ et courbes/.
                "Répertoire de la librairie": {
                    "type": "file",
                    "fileMode": "Directory",
                    "default": "",
                    "key": "library_dir",
                },
            },
        },
    }
