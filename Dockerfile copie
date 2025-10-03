# 1. Partir d'une image Python officielle et légère
FROM python:3.12-slim

# 2. Installer les dépendances système, y compris celles pour WeasyPrint
RUN apt-get update && apt-get install -y \
    libstdc++6 \
    libpango-1.0-0 \
    libharfbuzz0b \
    libpangoft2-1.0-0 \
    && rm -rf /var/lib/apt/lists/*

# 3. Définir le dossier de travail dans le conteneur
WORKDIR /app

# 4. Copier uniquement les dépendances pour optimiser le cache
COPY requirements.txt ./

# 5. Installer les dépendances Python
RUN pip install --no-cache-dir -r requirements.txt

# 6. Copier tout le reste de notre application
COPY . .

# 7. Laisser Railway gérer la commande de démarrage (il lira le Procfile)