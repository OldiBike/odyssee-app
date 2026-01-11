# 1. Partir d'une image Python officielle et légère
FROM python:3.12-slim

# 2. Installer les dépendances système, y compris CELLES POUR WEASYPRINT
RUN apt-get update && apt-get install -y \
    build-essential \
    libffi-dev \
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    libcairo2 \
    libgobject-2.0-0 \
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

