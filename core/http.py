"""
Session HTTP partagée de BSMB (issue #11).

Tous les appels réseau passent par `get_session()` :
  - une seule `requests.Session` (keep-alive, pool de 16 connexions) ;
  - un `User-Agent` qui identifie BSMB ;
  - des reprises automatiques (backoff exponentiel) sur 429 / 500 / 502 / 503 / 504
    et sur les erreurs de connexion, en respectant `Retry-After` (borné à ATTENTE_MAX) ;
  - un limiteur global (`RateLimiter`) : au plus MAX_SIMULTANES requêtes en vol quel que soit
    `max_workers`, et pause jusqu'à `RateLimit-Reset`, par endpoint, quand `RateLimit-Remaining` passe
    sous 5 % de `RateLimit-Limit`.

Aucun code au niveau module au-delà des définitions : la session est créée à la demande.
"""

import logging
import threading
import time
from contextlib import contextmanager
from urllib.parse import urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from core.version import __version__

log = logging.getLogger("bsmb.http")

USER_AGENT = f"BSMB/{__version__} (+https://github.com/Gotcha26/Bluesky-Save-My-Bookmarks)"
FRACTION_SEUIL = 0.05  # on attend la réinitialisation quand il reste au plus 5 % du quota
SEUIL_RESTANT_DEFAUT = 10  # seuil absolu quand `RateLimit-Limit` est absent
ATTENTE_MAX = 300  # secondes : borne d'une pause (limiteur et Retry-After)
MAX_SIMULTANES = 8  # requêtes en vol en même temps, tous threads confondus
TAILLE_POOL = 16


class _Retry(Retry):
    """Retry dont l'attente dictée par `Retry-After` est bornée à ATTENTE_MAX."""

    def get_retry_after(self, response):
        attente = super().get_retry_after(response)
        return None if attente is None else min(attente, ATTENTE_MAX)


def _entier(valeur):
    try:
        return int(float(valeur))
    except (TypeError, ValueError):
        return None


class RateLimiter:
    """Borne la concurrence et respecte les en-têtes `RateLimit-*` de l'API.

    Bluesky applique des quotas différents selon l'endpoint (30 par fenêtre pour `createSession`,
    3000 pour les appels publics) : l'état est mémorisé par clé `hôte + chemin`, et une pause
    ne retarde que les requêtes vers la même clé. Le seuil est proportionnel au quota
    (`RateLimit-Limit`), avec un repli absolu quand cet en-tête manque.

    `horloge` et `sleep` sont injectables pour les tests.
    """

    def __init__(
        self,
        seuil_defaut=SEUIL_RESTANT_DEFAUT,
        fraction=FRACTION_SEUIL,
        attente_max=ATTENTE_MAX,
        max_simultanes=MAX_SIMULTANES,
        horloge=time.time,
        sleep=time.sleep,
    ):
        self.seuil_defaut = seuil_defaut
        self.fraction = fraction
        self.attente_max = attente_max
        self.max_simultanes = max_simultanes
        self._horloge = horloge
        self._sleep = sleep
        self._semaphore = threading.Semaphore(max_simultanes)
        self._etat = threading.Lock()  # protège _reprises, _infos et _pauses
        self._reprises = {}  # clé -> epoch avant lequel on ne lance plus de requête vers cette clé
        self._infos = {}  # clé -> (restant, limite) du dernier quota bas (pour le journal)
        self._pauses = {}  # clé -> verrou : un seul thread dort, les autres attendent derrière

    @staticmethod
    def _cle(url):
        parts = urlparse(str(url))
        return f"{parts.netloc}{parts.path}"

    def _seuil(self, limite):
        if limite is None:
            return self.seuil_defaut
        return max(1, limite * self.fraction)

    @contextmanager
    def creneau(self):
        """Occupe une des places simultanées."""
        with self._semaphore:
            yield

    def observer(self, response, **kwargs):
        """Hook `response` : lit RateLimit-Remaining / -Limit / -Reset pour l'endpoint appelé."""
        restant = _entier(response.headers.get("RateLimit-Remaining"))
        limite = _entier(response.headers.get("RateLimit-Limit"))
        reset = _entier(response.headers.get("RateLimit-Reset"))
        if restant is None or reset is None or restant > self._seuil(limite):
            return
        if reset <= self._horloge():
            return
        cle = self._cle(response.url)
        with self._etat:
            self._reprises[cle] = max(self._reprises.get(cle, 0.0), float(reset))
            self._infos[cle] = (restant, limite)

    def attendre(self, url):
        """Dort (par tranches de 1 s) tant que la fenêtre de débit de cet endpoint n'est pas rouverte."""
        cle = self._cle(url)
        with self._etat:
            if cle not in self._reprises:
                return
            verrou = self._pauses.setdefault(cle, threading.Lock())
        with verrou:
            with self._etat:
                cible = self._reprises.get(cle, 0.0)
                duree = min(cible - self._horloge(), self.attente_max)
                restant, limite = self._infos.get(cle, (None, None))
            if duree <= 0:
                return
            quota = f"{restant}/{limite}" if limite is not None else f"{restant}"
            log.warning(
                "Limite de débit proche (RateLimit-Remaining=%s sur %s) : pause de %.0f s",
                quota,
                urlparse(str(url)).path,
                duree,
            )
            ecoule = 0.0
            while ecoule < duree:
                tranche = min(1.0, duree - ecoule)
                self._sleep(tranche)
                ecoule += tranche
            with self._etat:
                # Pause bornée : si Reset était plus loin que la borne, on repart quand même
                # (sauf si une réponse arrivée entre-temps a fixé une échéance plus récente)
                if self._reprises.get(cle) == cible:
                    del self._reprises[cle]


class _AdaptateurBsmb(HTTPAdapter):
    """Adaptateur qui passe chaque échange HTTP (reprises urllib3 comprises) par le limiteur.

    Le créneau est pris ici et non dans `Session.send` : `Session.send` est réentrant
    (il rappelle `self.send` à chaque redirection), ce qui ferait redemander un créneau
    à un thread qui en tient déjà un (interblocage). `HTTPAdapter.send` n'est jamais
    réentrant : chaque saut de redirection prend puis rend son propre créneau."""

    def __init__(self, limiteur, **kwargs):
        super().__init__(**kwargs)
        self.limiteur = limiteur

    def send(self, request, **kwargs):
        self.limiteur.attendre(request.url)
        with self.limiteur.creneau():
            return self._envoyer(request, **kwargs)

    def _envoyer(self, request, **kwargs):
        return super().send(request, **kwargs)


def build_session(limiteur=None):
    """Construit une session configurée (utile aux tests ; le code appelle `get_session()`)."""
    limiteur = limiteur or RateLimiter()
    session = requests.Session()
    session.hooks["response"].append(limiteur.observer)
    session.headers["User-Agent"] = USER_AGENT
    retry = _Retry(
        total=4,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET", "POST"],
        respect_retry_after_header=True,
        raise_on_status=False,
    )
    adaptateur = _AdaptateurBsmb(
        limiteur, pool_connections=TAILLE_POOL, pool_maxsize=TAILLE_POOL, max_retries=retry
    )
    session.mount("http://", adaptateur)
    session.mount("https://", adaptateur)
    return session


_session = None
_verrou_creation = threading.Lock()


def get_session():
    """Session partagée du processus (créée au premier appel)."""
    global _session
    if _session is None:
        with _verrou_creation:
            if _session is None:
                _session = build_session()
    return _session
