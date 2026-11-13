@echo off
rem Construit dist\CoolingTool.exe (un seul fichier). A lancer dans l'environnement Python
rem du projet, depuis ce dossier.
python -m qtsocle.build main.py --name CoolingTool --icon ressources\icons\icon.ico --data ressources
