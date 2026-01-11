# Résolution de l'erreur 508 - Insufficient Resource

## Problème identifié

L'application Railway fonctionne correctement, mais le serveur d'hébergement `voyages-privileges.be` retourne une erreur **508 Insufficient Resource** lors de l'upload des fichiers HTML via l'API `upload.php`.

### Logs d'erreur
```
❌ Erreur API (HTTP 508): 
508 Insufficient Resource
The website is temporarily unable to service your request as it exceeded resource limit.
```

## Causes possibles

1. **Limites PHP trop basses** sur votre hébergement web
2. **Mémoire insuffisante** pour traiter les fichiers base64
3. **Timeout d'exécution** dépassé
4. **Quota de ressources** atteint chez votre hébergeur

## Solutions

### Solution 1 : Augmenter les limites PHP (RECOMMANDÉ)

Vous devez modifier la configuration PHP de votre hébergeur. Ajoutez ou modifiez ces valeurs dans le fichier `upload.php` ou dans un fichier `.htaccess` :

#### Option A : Dans upload.php (au début du fichier)
```php
<?php
// Augmenter les limites PHP
ini_set('memory_limit', '256M');
ini_set('max_execution_time', '120');
ini_set('post_max_size', '20M');
ini_set('upload_max_filesize', '20M');

// Reste du code...
```

#### Option B : Dans .htaccess (à la racine du site)
```apache
php_value memory_limit 256M
php_value max_execution_time 120
php_value post_max_size 20M
php_value upload_max_filesize 20M
```

### Solution 2 : Optimiser upload.php

Assurez-vous que `upload.php` gère correctement les gros fichiers base64 :

```php
<?php
// Configuration
ini_set('memory_limit', '256M');
ini_set('max_execution_time', '120');

// Headers
header('Content-Type: application/json');

// Vérifier la clé API
$headers = getallheaders();
$apiKey = $headers['X-Api-Key'] ?? '';

if ($apiKey !== 'SecretUploadKey2025') {
    http_response_code(403);
    echo json_encode(['success' => false, 'error' => 'Unauthorized']);
    exit;
}

// Récupérer les données
$input = file_get_contents('php://input');
$data = json_decode($input, true);

if (!$data || !isset($data['filename']) || !isset($data['content']) || !isset($data['directory'])) {
    http_response_code(400);
    echo json_encode(['success' => false, 'error' => 'Missing parameters']);
    exit;
}

// Décoder le contenu base64
$content = base64_decode($data['content']);
if ($content === false) {
    http_response_code(400);
    echo json_encode(['success' => false, 'error' => 'Invalid base64 content']);
    exit;
}

// Créer le dossier si nécessaire
$directory = rtrim($data['directory'], '/');
if (!is_dir($directory)) {
    mkdir($directory, 0755, true);
}

// Sauvegarder le fichier
$filepath = $directory . '/' . basename($data['filename']);
$result = file_put_contents($filepath, $content);

if ($result === false) {
    http_response_code(500);
    echo json_encode(['success' => false, 'error' => 'Failed to write file']);
    exit;
}

// Succès
$url = 'https://www.voyages-privileges.be/' . $filepath;
echo json_encode([
    'success' => true,
    'url' => $url,
    'size' => strlen($content)
]);
```

### Solution 3 : Contacter votre hébergeur

Si les solutions ci-dessus ne fonctionnent pas, contactez votre hébergeur pour :
- Augmenter les limites de ressources PHP
- Vérifier si vous avez atteint un quota
- Demander des logs détaillés de l'erreur 508

## Modifications apportées au code Railway

Pour pallier temporairement au problème, j'ai ajouté :

1. **Système de retry** : L'application réessaie automatiquement 3 fois avec un délai croissant (2s, 4s, 8s)
2. **Timeout augmenté** : De 30s à 60s pour les gros fichiers
3. **Logs détaillés** : Pour mieux diagnostiquer les problèmes
4. **Gestion spécifique du 508** : Détection et retry automatique

## Test de la solution

Une fois les limites PHP augmentées, réessayez de publier une fiche hôtel. Les logs devraient montrer :
```
📤 Upload via API: fichier.html vers offres/
   Taille: 38.90 KB
✅ Upload réussi: https://www.voyages-privileges.be/offres/fichier.html
```

## Vérification rapide

Pour vérifier les limites PHP actuelles de votre serveur, créez un fichier `phpinfo.php` :
```php
<?php phpinfo(); ?>
```

Uploadez-le sur votre serveur et accédez à `https://www.voyages-privileges.be/phpinfo.php`

Cherchez ces valeurs :
- `memory_limit` (doit être >= 128M)
- `max_execution_time` (doit être >= 60)
- `post_max_size` (doit être >= 10M)

**N'oubliez pas de supprimer phpinfo.php après vérification pour des raisons de sécurité !**
