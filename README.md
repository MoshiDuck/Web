
## GIT

### Réinitialiser

1. Supprimer l'historique Git local + recrée un dépôt Git vierge
    ```bash
   Remove-Item -Recurse -Force .git
   ```
   
2. Init git
    ```bash       
   git init
   ```
   
3. Ajoutez les dossiers
   ```bash
   git add README.md
   ```
   
4. Init git
   ```bash       
   git branch -M main
   ```
   
5. Commit  
    ```bash
    git commit -m "[FAIT]"
    ```
   
6. Mettre main
   ```bash  
   git checkout -b main
   ```
   
7. Lier au dépôt distant GitHub
    ```bash
   git remote add origin https://github.com/MoshiDuck/Web
   ```
---

### Ajouter / Modifier

1. Ajoutez les dossiers  
    ```bash
   git add .
    ```
   
2. Commit  
    ```bash
    git commit -m "[FAIT] v"
    ```
   
3. Force le push  
    ```bash
    git push --force origin main
    ```
// Faire en sorte que ça soit adapter au telephone aussi taille ecran 