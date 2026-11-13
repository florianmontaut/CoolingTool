# ressources/app_settings.py
"""
Schéma des options de l'application (voir qtsocle.options_panel) : un onglet par groupe
de premier niveau, « key » est le nom de l'option dans les réglages.
"""


def schema(default_library: str) -> dict:
    return {
        "Général": {
            "type": "group",
            "children": {
                # par défaut la librairie livrée avec l'application ; pas encore pris en
                # compte (étape « librairie » de l'interface)
                "Répertoire de la librairie": {
                    "type": "file",
                    "fileMode": "Directory",
                    "default": default_library,
                    "key": "library_dir",
                },
            },
        },
    }
