import os
import re
import shutil
import subprocess
import tarfile
import tkinter as tk
import zipfile
from json import JSONDecodeError
from pathlib import Path
from tkinter import filedialog

from pyOneFichierClient.OneFichierAPI.exceptions import FichierSyntaxError, FichierResponseNotOk
from pyOneFichierClient.OneFichierAPI.py1FichierClient import s
from requests_toolbelt import MultipartEncoder, MultipartEncoderMonitor

LINKVERTISE_USER_ID = "1365582"
LINKVERTISE_DOMAIN = "https://link-to.net"
CONFIG_1FICHIER = {
    "api_key": "VqRfSWgCcbCqSytOBeoUsNL83Hg8nd0t"
}

# Extensions prises en charge
ARCHIVE_EXTS = ['.zip', '.tar', '.tar.gz', '.tar.bz2', '.tar.xz', '.rar']
IMAGE_EXTS = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp'}
VIDEO_EXTS = {'.mp4', '.mov', '.avi', '.mkv', '.webm'}

BASE_DIR    = Path(__file__).resolve().parent
CODES_FILE =BASE_DIR / "codes.txt"
ARCHIVES_DIR = BASE_DIR / "archives"
IMAGES_DIR   = BASE_DIR / "images"
FFMPEG_PATH = BASE_DIR / "Ressource" / "ffmpeg" / "bin" / "ffmpeg.exe"
FFPROBE_PATH = BASE_DIR / "Ressource" / "ffmpeg" / "bin" / "ffprobe.exe"
UNRAR_PATH = BASE_DIR / "Ressource" / "unrar" / "UnRAR.exe"
INVALID_CHARS        = r'[<>:"/\\|?*]'
TRAILING_DOTS_SPACES = r'[\. ]+$'

HTML_HEAD = f"""<!DOCTYPE html>
<html lang=\"fr\">
<head>
  <meta charset=\"UTF-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\" />
  <title>Galerie de Téléchargement</title>
  <style>
    body {{ font-family: sans-serif; margin: 2rem; }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
      gap: 1rem;
    }}
    .card {{
      border: 1px solid #ddd;
      border-radius: 8px;
      overflow: hidden;
      text-align: center;
      background: #f9f9f9;
    }}
    .card img {{ display: block; max-width: 100%; height: auto; background: #fff; }}
    .card-title {{ margin: 0.5rem; font-size: 1rem; }}
    .card a {{ display: block; text-decoration: none; color: #333; padding: 0.5rem; }}
    .card a:hover {{ background: #f0f0f0; }}
  </style>
  <!-- Linkvertise Web Snippet -->
  <script src=\"https://publisher.linkvertise.com/cdn/linkvertise.js\"></script>
  <script>linkvertise({LINKVERTISE_USER_ID},{{ whitelist:[], blacklist:[] }});</script>
</head>
<body>
  <h1>Galerie de Téléchargement</h1>
  <div class=\"grid\">"""

HTML_TAIL = """
  </div>
</body>
</html>
"""

def make_card(filename: str, code: str) -> str:
    name = Path(filename).stem
    # vignette
    thumb = None
    for ext in IMAGE_EXTS:
        p = IMAGES_DIR / f"{sanitize_name(name)}{ext}"
        if p.exists():
            thumb = p.name
            break
    img_src = f"images/{thumb}" if thumb else "https://via.placeholder.com/200x150?text=No+Thumb"
    raw_aff = f"https://1fichier.com/?{code}&af=5091183"
    return f"""
    <div class="card">
      <a href="{raw_aff}" target="_blank">
        <img src="{img_src}" alt="{name}" />
        <div class="card-title">{name}</div>
      </a>
    </div>
    """


def get_first_video(folder: Path) -> Path | None:
    """
    Parcourt récursivement `folder` et renvoie le premier fichier vidéo
    trouvé (selon VIDEO_EXTS), ou None s'il n'y en a pas.
    """
    for root, _, files in os.walk(folder):
        for fname in files:
            if Path(fname).suffix.lower() in VIDEO_EXTS:
                return Path(root) / fname
    return None

def sanitize_name(name: str) -> str:
    clean = re.sub(INVALID_CHARS, '_', name)
    clean = re.sub(TRAILING_DOTS_SPACES, '', clean)
    return clean or "archive"

def upload_to_1fichier(client, file_path: Path) -> str:
    """Envoie le fichier sur 1fichier.com et renvoie le lien de téléchargement."""
    # Obtention du serveur d'upload
    resp = client.api_call(
        'https://api.1fichier.com/v1/upload/get_upload_server.cgi', method='GET'
    )
    up_srv = resp['url']
    upload_id = resp['id']
    last_printed = {'pct': -10}

    def progress_callback(monitor):
        pct = int(100 * monitor.bytes_read / monitor.len)
        # on print seulement aux multiples de 10 et une seule fois chacun
        if pct % 10 == 0 and pct != last_printed['pct']:
            print(f"Progression upload: {pct}%")
            last_printed['pct'] = pct

    with open(file_path, 'rb') as f:
        encoder = MultipartEncoder({'file[]': (file_path.name, f, 'application/octet-stream')})
        monitor = MultipartEncoderMonitor(encoder, progress_callback)


        headers = {'Content-Type': monitor.content_type}
        if client.authed:
            headers.update(client.auth_nc)

        url = f'https://{up_srv}/upload.cgi?id={upload_id}'
        r = s.post(url, data=monitor, headers=headers, allow_redirects=False)
        if 'Location' not in r.headers:
            raise FichierResponseNotOk('Header Location manquant')

        loc = r.headers['Location']
        r2 = s.get(f'https://{up_srv}{loc}')
        m = re.search(r'<td class="normal"><a href="(.+)">', r2.text)
        if not m:
            raise FichierResponseNotOk('Lien de téléchargement introuvable')

        return m.group(1).split('?')[1]

def extract_rar_with_unrar(archive_path: str, dest_dir: Path) -> bool:
    cmd = [
        str(UNRAR_PATH),
        'x', '-o+', '-inul',
        archive_path,
        str(dest_dir)
    ]
    try:
        subprocess.run(cmd, check=True)
        print(f"[OK–unrar] {archive_path} → {dest_dir}")
        return True
    except FileNotFoundError:
        print(f"[ERREUR–unrar] impossible de trouver {UNRAR_PATH}. Vérifiez votre installation de unrar.")
        return False
    except Exception as e:
        print(f"[ERREUR–unrar] échec extraction {archive_path} : {e}")
        return False

def extract_zip_or_tar(archive_path: str, dest_dir: Path):
    """
    Extrait ZIP ou TAR en nettoyant chaque segment de chemin interne.
    """
    if archive_path.lower().endswith('.zip'):
        opener, members = (zipfile.ZipFile, lambda z: z.infolist())
        open_kwargs = {}
    else:
        opener, members = (tarfile.open, lambda t: t.getmembers())
        open_kwargs = {"mode": "r:*"}

    with opener(archive_path, **open_kwargs) as archive:
        for member in members(archive):
            # Récupérer le chemin interne
            raw_path = member.filename if isinstance(member, zipfile.ZipInfo) else member.name
            # Séparer les composants, nettoyer puis reformer
            parts = [sanitize_name(p) for p in Path(raw_path).parts if p not in ("", ".", "..")]
            if not parts:
                continue
            target_path = dest_dir.joinpath(*parts)

            # Si c'est un répertoire
            if raw_path.endswith(('/', '\\')) or (hasattr(member, 'isdir') and member.isdir()):
                target_path.mkdir(parents=True, exist_ok=True)
            else:
                target_path.parent.mkdir(parents=True, exist_ok=True)
                # Extraction fichier
                if isinstance(member, zipfile.ZipInfo):
                    with archive.open(member) as src, open(target_path, 'wb') as dst:
                        shutil.copyfileobj(src, dst)
                else:
                    f = archive.extractfile(member)
                    if f:
                        with f, open(target_path, 'wb') as dst:
                            shutil.copyfileobj(f, dst)
    print(f"[OK]      {archive_path} → {dest_dir}")

def extract_media_fallback(archive_name: str, folder: Path):
    """
    Si pas d'image, prend la première vidéo de `folder` et génère un GIF de 5s
    dans IMAGES_DIR/<archive_name>.gif via ffmpeg.
    """
    video = get_first_video(folder)
    if not video:
        print(f"[SKIP] Pas de vidéo pour {archive_name}, on ne crée pas de GIF.")
        return

    dest = IMAGES_DIR / f"{archive_name}.gif"
    print(f"[DEBUG] Création du GIF de fallback pour {archive_name} → {dest.name}")

    if dest.exists():
        print(f"[SKIP] {dest.name} existe déjà")
        return

    cmd = [
        str(FFMPEG_PATH),
        '-y',
        '-i', str(video),
        '-t', '5',
        '-vf', 'fps=10,scale=320:-1:flags=lanczos',
        str(dest)
    ]
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print(f"[OK–gif] {video.relative_to(BASE_DIR)} → {dest.relative_to(BASE_DIR)}")
    except subprocess.CalledProcessError as e:
        print(f"[ERREUR–gif] échec conversion {video} : {e}")

def extract_archive(archive_path: str):
    base = os.path.basename(archive_path)
    # Retirer l'extension multiple
    name = base
    for ext in ARCHIVE_EXTS:
        if name.lower().endswith(ext):
            name = name[:-len(ext)]
            break

    safe_name = sanitize_name(name)
    dest_dir   = ARCHIVES_DIR / safe_name

    # Skip si déjà extrait
    if dest_dir.exists():
        print(f"[SKIP]    {archive_path} → {dest_dir} (existe déjà)")
        return

    dest_dir.mkdir(parents=True, exist_ok=True)

    # Choix de la méthode selon l'extension
    if archive_path.lower().endswith('.rar'):
        extract_rar_with_unrar(archive_path, dest_dir)
    else:
        try:
            extract_zip_or_tar(archive_path, dest_dir)
        except Exception as e:
            print(f"[ERREUR]  impossible d'extraire {archive_path} : {e}")

def get_first_image(folder: Path) -> Path | None:
    """
    Parcourt récursivement `folder` et renvoie le premier fichier
    dont l'extension est dans IMAGE_EXTS, ou None si aucune image.
    """
    for root, _, files in os.walk(folder):
        for fname in files:
            if Path(fname).suffix.lower() in IMAGE_EXTS:
                return Path(root) / fname
    return None

def collect_first_images():
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    print(f"[INFO] Début de la collecte des images ({len(list(ARCHIVES_DIR.iterdir()))} dossiers à traiter)")

    for sub in ARCHIVES_DIR.iterdir():
        if not sub.is_dir():
            continue

        print(f"\n[DEBUG] Traitement du dossier extrait : {sub.name}")

        # 1) Recherche d’une image
        first_img = get_first_image(sub)
        if first_img:
            dest = IMAGES_DIR / f"{sub.name}{first_img.suffix.lower()}"
            try:
                shutil.copy2(first_img, dest)
                print(f"[OK]    Copie de l’image {first_img.relative_to(BASE_DIR)} → {dest.relative_to(BASE_DIR)}")
            except Exception as e:
                print(f"[ERREUR] Échec copie {first_img} → {dest} : {e}")
            continue

        # 2) Pas d’image trouvée
        print(f"[INFO] Pas d’image dans « {sub.name} ». Lancement du fallback vidéo…")

        # 3) Fallback vidéo
        video = get_first_video(sub)
        if video:
            print(f"[DEBUG]   Première vidéo trouvée : {video.relative_to(BASE_DIR)}")
            extract_media_fallback(sub.name, sub)
        else:
            print(f"[SKIP]   Aucune vidéo non plus dans « {sub.name} ». Pas de vignette générée.")

def build_gallery_html_string(codes):
    """
    codes: liste de noms de fichiers (ex. ['1499 dezomorfina.zip', ...])
    Retourne la chaîne HTML complète de la galerie, sans l’écrire sur le disque.
    """
    html = [HTML_HEAD]

    placeholder = "https://via.placeholder.com/200x150?text=No+Thumb"
    for archive_name in codes:
        stem = Path(archive_name).stem
        safe = sanitize_name(stem)

        # cherche la vignette locale
        thumb = None
        for img in IMAGES_DIR.iterdir():
            if img.stem == safe:
                thumb = img.name
                break

        # si pas de vignette, on utilisera le placeholder
        img_src = f"images/{thumb}" if thumb else placeholder

        # lien 1fichier déjà récupéré dans `codes` (tu peux remplacer par le lien direct)
        # ici on suppose que `codes` est une liste de tuples (archive_name, code_1fichier)
        # sinon adapte pour récupérer `code` depuis ton stockage en mémoire
        code_1fichier = codes[archive_name]
        raw_aff = f"https://1fichier.com/?{code_1fichier}&af=5091183"

        html.append(f'''
    <div class="card">
      <a href="{raw_aff}" target="_blank">
        <img src="{img_src}" alt="{stem}" />
        <div class="card-title">{stem}</div>
      </a>
    </div>
        ''')

    html.append(HTML_TAIL)
    return "".join(html)

class FichierClient:
    def __init__(self):
        self.auth = {'Content-Type':'application/json'}
        self.auth_nc = {}
        self.authed = False
        key = CONFIG_1FICHIER['api_key']
        if key:
            self.auth['Authorization'] = f"Bearer {key}"
            self.auth_nc = {'Authorization': f"Bearer {key}"}
            self.authed = True

    def api_call(self, url, json_data=None, method='POST'):
        if method == 'POST':
            r = s.post(url, json=json_data, headers=self.auth)
        elif method == 'GET':
            r = s.get(url, headers=self.auth)
        else:
            raise FichierSyntaxError(f'Method {method} not available/implemented')

        if r.ok:
            try:
                o = r.json()
            except JSONDecodeError:
                raise FichierResponseNotOk(f'1fichier returned malformed json')
            if 'status' in o:
                if o['status'] == 'OK':
                    return r.json()
                else:
                    message = r.json()['message']
                    raise FichierResponseNotOk(f'Response from 1fichier: {message!r}')
            else:
                return o
        else:
            raise FichierResponseNotOk(f'HTTP Response code from 1fichier: {r.status_code} {r.reason}')

def main():
    # 1. Préparation des dossiers
    ARCHIVES_DIR.mkdir(parents=True, exist_ok=True)
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    if not CODES_FILE.exists():
        CODES_FILE.touch()
        print(f"[INFO] Création de {CODES_FILE}")

    # 2. Chargement des archives déjà traitées et de leurs codes si présents
    processed = set()
    codes_map = {}
    with CODES_FILE.open("r", encoding="utf-8") as f:
        for line in f:
            entry = line.strip()
            if not entry:
                continue
            parts = entry.split("|", 1)
            name = parts[0]
            processed.add(name)
            if len(parts) == 2 and parts[1]:
                codes_map[name] = parts[1]
    print(f"[INFO] {len(processed)} archive(s) déjà enregistrée(s) dans codes.txt")

    # 3. Sélection du dossier source
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    source_folder = filedialog.askdirectory(title="Sélectionnez le dossier contenant les archives")
    if not source_folder:
        print("[ERREUR] Aucun dossier sélectionné. Fin.")
        return
    print(f"[INFO] Dossier source : {source_folder}")

    client = FichierClient()

    # 4. Recherche des archives
    archives = [
        f for f in os.listdir(source_folder)
        if Path(source_folder, f).is_file() and Path(f).suffix.lower() in ARCHIVE_EXTS
    ]
    print(f"[INFO] {len(archives)} archive(s) détectée(s)")

    # 5. Upload, extraction et enregistrement des nouveaux
    for entry in archives:
        if entry in processed:
            print(f"[SKIP] {entry} déjà traité")
            continue

        path = Path(source_folder) / entry
        print(f"=== Traitement et upload de {entry} ===")
        try:
            link_code = upload_to_1fichier(client, path)
            print(f"[DEBUG] Lien retourné : {link_code}")
        except Exception as e:
            print(f"[UPLOAD ERREUR] {e}")
            continue

        # Stockage
        codes_map[entry] = link_code
        with CODES_FILE.open("a", encoding="utf-8") as f:
            f.write(f"{entry}|{link_code}\n")
        processed.add(entry)
        print(f"[OK] '{entry}' ajouté à codes.txt")

        # Extraction
        extract_archive(str(path))

    # 6. Création des vignettes
    collect_first_images()

    # 7. Génération HTML de la galerie
    html_content = build_gallery_html_string(codes_map)
    output_file = BASE_DIR / "index.html"
    with output_file.open("w", encoding="utf-8") as f:
        f.write(html_content)
    print(f"[OK] Galerie HTML générée dans {output_file}")

    # 8. Nettoyage des dossiers extraits
    print("[INFO] Nettoyage des dossiers d'archives…")
    for sub in ARCHIVES_DIR.iterdir():
        if sub.is_dir():
            try:
                shutil.rmtree(sub)
                print(f"[OK] Suppression de {sub.name}")
            except Exception as e:
                print(f"[ERREUR] Impossible de supprimer {sub.name} : {e}")

if __name__ == "__main__":
    main()
