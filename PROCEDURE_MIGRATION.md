Guide de Mise à Jour de la Base de Données sur Railway
Ce document explique la procédure à suivre pour mettre à jour la structure de la base de données de l'application Odyssée après avoir modifié le fichier models.py.

Quand utiliser cette procédure ?
Vous devez suivre cette procédure uniquement si vous avez modifié la structure de la base de données, par exemple en :

Ajoutant une nouvelle colonne à la table Trip.

Modifiant le type d'une colonne.

Ajoutant une nouvelle table.

Étape 1 : Modifier le code et le déployer
Modifiez votre code : Apportez les changements nécessaires à votre fichier models.py.

Envoyez les modifications sur GitHub : Ouvrez votre terminal sur votre Mac, dans le dossier du projet, et lancez les commandes suivantes :

Bash

# Ajoute toutes les modifications
git add .

# Enregistre les modifications avec un message descriptif
git commit -m "Description de la modification (ex: Ajout du champ 'facture_pdf')"

# Envoie les modifications sur GitHub
git push
Attendez le déploiement : Le git push va automatiquement déclencher un nouveau déploiement sur Railway. Attendez qu'il soit terminé avec succès (coche verte ✅). À ce stade, votre code est à jour, mais la base de données n'a pas encore changé.

Étape 2 : Appliquer la mise à jour à la base de données
C'est l'étape la plus importante. Nous utilisons railway ssh pour nous connecter directement au serveur de l'application.

Connectez-vous au terminal du serveur : Dans votre terminal Mac, lancez la commande :

Bash

railway ssh
Si on vous demande de choisir un service, sélectionnez web. Le prompt de votre terminal devrait changer pour ressembler à root@...:/app#.

Créez le fichier de migration : Cette commande compare votre models.py à l'état de la base de données et génère un script de mise à jour.

Bash

flask db migrate -m "un_nom_pour_votre_migration"
Appliquez la migration : Cette commande exécute le script et modifie réellement la base de données.

Bash

flask db upgrade
Quittez le terminal du serveur : Une fois la commande terminée, tapez exit pour revenir à votre terminal Mac.

Bash

exit
À ce stade, votre base de données en production est à jour et fonctionnelle.

Étape 3 : Synchroniser le nouveau fichier de migration
Un nouveau fichier de migration a été créé sur le serveur. Pour garder votre projet propre et éviter des problèmes futurs, il faut le rapatrier sur votre Mac et l'ajouter à GitHub.

Créez le même fichier de migration sur votre Mac : Dans votre terminal Mac (pas celui de ssh), relancez la même commande migrate.

Bash

flask db migrate -m "un_nom_pour_votre_migration"
Cela va créer le fichier manquant dans votre dossier local migrations/versions/.

Envoyez ce nouveau fichier sur GitHub :

Bash

git add .
git commit -m "Ajout du nouveau fichier de migration"
git push
Cela va déclencher un dernier déploiement sur Railway, qui sera très rapide.

Votre projet est maintenant parfaitement synchronisé.

🚨 Dépannage : Que faire en cas d'erreur Can't locate revision identified by ... ?
Cette erreur signifie que l'historique de votre base de données est désynchronisé. Voici la procédure de réparation "nucléaire" que nous avons validée ensemble.

Connectez-vous au serveur avec railway ssh.

Identifiez la dernière migration valide qui existe réellement dans vos fichiers sur le serveur :

Bash

ls -la migrations/versions/
Repérez le nom du fichier le plus récent (par exemple, 285c37d40279_... .py). Le numéro de révision est 285c37d40279.

Lancez le script Python de réinitialisation : Exécutez cette commande en une seule ligne, en remplaçant NUMERO_DE_LA_DERNIERE_VERSION par la révision que vous avez identifiée à l'étape précédente.

Python

python -c "from app import create_app, db; from sqlalchemy import text; app = create_app(); app.app_context().push(); db.session.execute(text('DELETE FROM alembic_version')); db.session.execute(text(\"INSERT INTO alembic_version (version_num) VALUES ('NUMERO_DE_LA_DERNIERE_VERSION')\")); db.session.commit(); print('✅ Historique réinitialisé.')"
Reprenez l'Étape 2 : Une fois la base de données réinitialisée, vous pouvez relancer les commandes flask db migrate et flask db upgrade normalement.