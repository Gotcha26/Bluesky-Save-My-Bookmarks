#!/usr/bin/env python3
"""
Archive fidèle d'un post Bluesky (issue #7), écrite dans le dossier des textes :
  <base>.json   fiche (sidecar) : record brut, postView hydraté s'il est connu, métadonnées
  <base>.txt    texte lisible : facets résolues, alt des médias, carte de lien, citation, réponse

<base> vaut <handle>_<YYYYMMDD>_<postid> (nom_base_texte) ou name_prefix pour un post cité.
Pas d'usage manuel : l'orchestrateur et les downloaders texte / external fournissent le record.
"""
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from core.version import __version__
from downloaders import DownloadError, DownloadResult
from downloaders.text import nom_base_texte

FACET_LIEN = "app.bsky.richtext.facet#link"


def bsmb_version():
    """Version de BSMB (source unique : core/version.py)."""
    return __version__


# -------------------- Facets --------------------
def _uri_du_lien(facet):
    """URI de la première feature `link` d'une facet, ou None."""
    for feature in facet.get("features") or []:
        if isinstance(feature, dict) and feature.get("$type") == FACET_LIEN and feature.get("uri"):
            return feature["uri"]
    return None


def resolve_facets(text, facets):
    """
    Texte d'un post où les liens affichent leur URL réelle : « libellé (https://url) ».

    Les index `byteStart` / `byteEnd` des facets sont des octets UTF-8. Les mentions
    (déjà écrites « @handle ») et les tags (« #tag ») restent tels quels. Une facet
    hors bornes, chevauchante (la première par `byteStart` est gardée ; à début égal, la plus courte),
    coupant un caractère ou malformée est ignorée.
    """
    if not text or not facets or not isinstance(facets, list):
        return text or ""
    brut = text.encode("utf-8")

    liens = []
    for facet in facets:
        if not isinstance(facet, dict) or not isinstance(facet.get("index"), dict):
            continue
        debut, fin = facet["index"].get("byteStart"), facet["index"].get("byteEnd")
        if not (isinstance(debut, int) and isinstance(fin, int)) or isinstance(debut, bool) or isinstance(fin, bool):
            continue
        if not 0 <= debut < fin <= len(brut):
            continue
        uri = _uri_du_lien(facet)
        if uri:
            liens.append((debut, fin, uri))
    liens.sort()

    morceaux = []
    curseur = 0
    for debut, fin, uri in liens:
        if debut < curseur:
            continue  # chevauche la facet précédente
        try:
            avant = brut[curseur:debut].decode("utf-8")
            libelle = brut[debut:fin].decode("utf-8")
        except UnicodeDecodeError:
            continue  # l'index coupe un caractère
        if libelle.rstrip("/") == uri.rstrip("/"):
            morceaux.append(avant + libelle)
        else:
            morceaux.append(f"{avant}{libelle} ({uri})")
        curseur = fin
    morceaux.append(brut[curseur:].decode("utf-8"))
    return "".join(morceaux)


# -------------------- Lecture du record --------------------
def _media_du_record(record):
    """Embed média du record (celui d'un recordWithMedia le cas échéant), ou {}."""
    embed = (record or {}).get("embed") or {}
    if embed.get("$type", "").startswith("app.bsky.embed.recordWithMedia"):
        return embed.get("media") or {}
    return embed


def _uri_citee(record):
    """AT-URI du record cité (embed.record ou recordWithMedia), ou ''."""
    embed = (record or {}).get("embed") or {}
    if embed.get("$type", "").startswith("app.bsky.embed.recordWithMedia"):
        embed = embed.get("record") or {}
    if embed.get("$type", "").startswith("app.bsky.embed.record"):
        return (embed.get("record") or {}).get("uri", "")
    return ""


def _lignes_alt(record, alts):
    """Lignes « [Image N : alt] » / « [Vidéo : alt] » (seulement pour un alt non vide)."""
    media = _media_du_record(record)
    type_media = media.get("$type", "")
    if type_media.startswith("app.bsky.embed.images"):
        libelle = "Image {n}"
        valeurs = [img.get("alt", "") for img in media.get("images") or []]
    elif type_media.startswith("app.bsky.embed.video"):
        libelle = "Vidéo"
        valeurs = [media.get("alt", "")]
    else:
        return []
    if alts is not None:
        valeurs = list(alts)
    return [f"[{libelle.format(n=n)} : {alt}]" for n, alt in enumerate(valeurs, start=1) if alt]


def _identite(post_url):
    """(handle ou DID, rkey) d'après l'URL du post ; DownloadError si ce n'est pas un post."""
    parts = urlparse(post_url).path.strip("/").split("/")
    if len(parts) < 4 or parts[0] != "profile" or parts[2] != "post":
        raise DownloadError(f"URL de post invalide : {post_url}")
    return parts[1], parts[-1]


def _nom_base(post_url, record, name_prefix):
    if name_prefix:
        return name_prefix
    handle, rkey = _identite(post_url)
    return nom_base_texte(handle, rkey, (record or {}).get("createdAt", ""))


def _contenu_texte(post_url, record, alts, auteur=None):
    handle, _ = _identite(post_url)
    lignes = [f"Post: {post_url}", f"Date: {record.get('createdAt', '')}", f"Auteur: {auteur or handle}"]
    langs = [la for la in record.get("langs") or [] if isinstance(la, str)]
    if langs:
        lignes.append(f"Langue: {', '.join(langs)}")
    lignes += ["", resolve_facets(record.get("text", ""), record.get("facets"))]

    blocs = []
    if alt := _lignes_alt(record, alts):
        blocs.append(alt)
    external = _media_du_record(record).get("external") or {}
    if external:
        blocs.append([f"Lien: {external.get('uri', '')}", f"Titre: {external.get('title', '')}",
                      f"Description: {external.get('description', '')}"])
    fin = []
    if citee := _uri_citee(record):
        fin.append(f"Cite: {citee}")
    if parent := ((record.get("reply") or {}).get("parent") or {}).get("uri"):
        fin.append(f"Réponse à: {parent}")
    if fin:
        blocs.append(fin)
    for bloc in blocs:
        lignes += [""] + bloc
    return "\n".join(lignes) + "\n"


# -------------------- Écriture --------------------
def _resultat(chemin, media_type):
    return DownloadResult(chemin.name, chemin, media_type, chemin.stat().st_size)


def write_text(post_url, record, dest_dir, config, name_prefix=None, alts=None, auteur=None):
    """
    Écrit <base>.txt : en-tête (Post, Date, Auteur, Langue), texte avec facets résolues,
    alt des médias, carte de lien, citation (Cite:) et parent d'une réponse (Réponse à:).

    record : record brut du post. alts : alt des médias dans l'ordre, qui remplacent ceux
    du record. auteur : handle affiché dans « Auteur: » (défaut : celui de l'URL ; le nom du fichier
    vient toujours de l'URL). Un fichier déjà présent au même nom et au même contenu n'est pas réécrit.

    Returns: [DownloadResult(media_type="text")]
    Raises: DownloadError (URL invalide, écriture impossible).
    """
    base = _nom_base(post_url, record, name_prefix)
    contenu = _contenu_texte(post_url, record or {}, alts, auteur)
    try:
        dest_dir = Path(dest_dir)
        dest_dir.mkdir(parents=True, exist_ok=True)
        chemin = dest_dir / f"{base}.txt"
        if not (chemin.is_file() and chemin.read_bytes() == contenu.encode("utf-8")):
            chemin.write_text(contenu, encoding="utf-8", newline="\n")
        return [_resultat(chemin, "text")]
    except OSError as e:
        raise DownloadError(f"Écriture du texte impossible : {e}") from e


def write_sidecar(post_url, record, post_view, dest_dir, config, name_prefix=None, at_uri=None):
    """
    Écrit <base>.json : {"url", "at_uri", "archived_at", "bsmb_version", "record", "post_view"}.

    record est le record brut (facets, langs, embed… intacts) ; post_view la vue hydratée
    (auteur, labels, embed `#view`) ou None. at_uri : à défaut, celui de la vue, puis une
    reconstruction à partir de l'URL du post. Le fichier est toujours réécrit.

    Returns: [DownloadResult(media_type="sidecar")]
    Raises: DownloadError (URL invalide, écriture impossible).
    """
    base = _nom_base(post_url, record, name_prefix)
    if not at_uri:
        auteur, rkey = _identite(post_url)
        at_uri = (post_view or {}).get("uri") or f"at://{auteur}/app.bsky.feed.post/{rkey}"
    fiche = {
        "url": post_url,
        "at_uri": at_uri,
        "archived_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "bsmb_version": bsmb_version(),
        "record": record,
        "post_view": post_view,
    }
    part = None
    try:
        dest_dir = Path(dest_dir)
        dest_dir.mkdir(parents=True, exist_ok=True)
        chemin = dest_dir / f"{base}.json"
        part = Path(f"{chemin}.part")
        part.write_text(json.dumps(fiche, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
        os.replace(part, chemin)
        part = None
        return [_resultat(chemin, "sidecar")]
    except OSError as e:
        raise DownloadError(f"Écriture de la fiche JSON impossible : {e}") from e
    finally:
        if part is not None and part.exists():
            part.unlink()
