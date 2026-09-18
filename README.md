# Catalogue de nouveautés

Application Streamlit personnelle pour transformer une liste Excel d'ouvrages
en catalogue PDF illustré avec les couvertures disponibles auprès de la BnF.

## État du projet

Cette troisième version permet :

- de déposer un fichier `.xls` ou `.xlsx` ;
- de choisir la feuille Excel ;
- d'associer les colonnes ISBN, titre, auteur, année, genre et cote ;
- d'isoler uniquement les données bibliographiques sélectionnées ;
- de vérifier les ISBN exploitables ;
- d'interroger l'API Couvertures de la BnF ;
- d'afficher une barre de progression et un bilan des résultats ;
- de prévisualiser les couvertures trouvées ;
- d'utiliser une vignette générique lorsqu'une couverture est absente ;
- de personnaliser le titre du catalogue ;
- de choisir 2, 4 ou 6 ouvrages par page ;
- de sélectionner les informations à afficher ;
- de générer et télécharger le catalogue PDF.

Le PDF est produit en mémoire et n'est pas enregistré dans le dépôt GitHub.

## Développement dans GitHub Codespaces

1. Ouvrir le dépôt sur GitHub.
2. Cliquer sur **Code**, puis **Codespaces** et **Create codespace on main**.
3. Dans le terminal du Codespace, exécuter :

```bash
python -m pip install -r requirements.txt
streamlit run streamlit_app.py
```

4. Lorsque GitHub signale que le port `8501` est disponible, cliquer sur
   **Open in Browser**.

## Développement local

```bash
python -m venv .venv
```

Activation sous Windows PowerShell :

```powershell
.venv\Scripts\Activate.ps1
```

Installation et lancement :

```bash
python -m pip install -r requirements.txt
streamlit run streamlit_app.py
```

## Confidentialité

Les fichiers Excel et PDF sont exclus du dépôt Git par `.gitignore`. Ne jamais
ajouter au dépôt un fichier contenant des données d'emprunteurs ou d'autres
données personnelles. Lors du déploiement en ligne, le fichier envoyé est traité
sur l'infrastructure de l'hébergeur.
