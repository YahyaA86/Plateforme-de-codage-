# Plateforme de codage

Plateforme de génération d'exercices de programmation corrigés automatiquement par une IA.

## Installation

### Prérequis communs

1. **Python 3.8+**
   - **Windows** : Télécharger sur [python.org](https://www.python.org/downloads/)
     - Cocher "Add Python to PATH" pendant l'installation
   - **MacOS** : Pré-installé ou via [Homebrew](https://brew.sh/): `brew install python`
   - **Linux** : Utiliser le gestionnaire de paquets
     - Debian/Ubuntu : `sudo apt install python3 python3-pip`
     - Fedora : `sudo dnf install python3`
   - Vérifier l'installation : `python --version` ou `python3 --version`

2. **Ollama**
   - Installer depuis [ollama.ai](https://ollama.ai/)
   - Après installation, télécharger le modèle requis (mistral) :
     ```bash
     ollama pull mistral
     ```
   - Vérifier que le service Ollama tourne en arrière-plan
3. **Dépendances Python**
   - Installer les dépendances avec :
     ```bash
     pip install -r requirements.txt
     ```
