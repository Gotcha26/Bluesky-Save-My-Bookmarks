"""
Session HTTP partagée de BSMB (issue #11).

Tous les appels réseau passent par `get_session()` :
  - une seule `requests.Session` (keep-alive, pool de 16 connexions) ;
  - un `User-Agent` qui identifie BSMB ;
  - des reprises automatiques (backoff exponentiel) sur 429 / 500 / 502 / 503 / 504
    et sur les erreurs de connexion, en respectant `Retry-After` (borné à ATTENTE_MAX) ;
  - un limiteur global (`RateLimiter`) : au plus MAX_SIMULTANES requêtes en vol quel que soit
    `max_workers`, et pause jusqu'à `RateLimit-Reset` quand `RateLimit-Remaining` passe sous le seuil.

Aucun code au niveau module au-delà des définitions : la session est créée à la demande.
"""
import logging
import threading
import time
from contextlib import contextmanager

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from core.version import __version__

log = logging.getLogger("bsmb.http")

USER_AGENT = f"BSMB/{__version__} (+https://github.com/Gotcha26/Bluesky-Save-My-Bookmarks)"
SEUIL_RESTANT = 50       # en dessous, on attend la réinitialisation de la fenêtre
ATTENTE_MAX = 300        # secondes : borne d'une pause (limiteur et Retry-After)
MAX_SIMULTANES = 8       # requêtes en vol en même temps, tous threads confondus
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

    `horloge` et `sleep` sont injectables pour les tests.
    """

    def __init__(self, seuil=SEUIL_RESTANT, attente_max=ATTENTE_MAX, max_simultanes=MAX_SIMULTANES,
                 horloge=time.time, sleep=time.sleep):
        self.seuil = seuil
        self.attente_max = attente_max
        self.max_simultanes = max_simultanes
        self._horloge = horloge
        self._sleep = sleep
        self._semaphore = threading.Semaphore(max_simultanes)
        self._etat = threading.Lock()     # protège _reprise
        self._pause = threading.Lock()    # un seul thread dort, les autres attendent derrière
        self._reprise = 0.0               # epoch avant lequel on ne lance plus de requête
        self._restant = None              # dernier RateLimit-Remaining bas (pour le journal)

    @contextmanager
    def creneau(self):
        """Occupe une des places simultanées."""
        with self._semaphore:
            yield

    def observer(self, response, **kwargs):
        """Hook `response` : lit RateLimit-Remaining / RateLimit-Reset."""
        restant = _entier(response.headers.get("RateLimit-Remaining"))
        reset = _entier(response.headers.get("RateLimit-Reset"))
        if restant is None or reset is None or restant >= self.seuil:
            return
        if reset <= self._horloge():
            return
        with self._etat:
            self._reprise = max(self._reprise, float(reset))
            self._restant = restant

    def attendre(self):
        """Dort (par tranches de 1 s) tant que la fenêtre de débit n'est pas rouverte."""
        with self._pause:
            with self._etat:
                cible = self._reprise
                duree = min(cible - self._horloge(), self.attente_max)
            if duree <= 0:
                return
            log.warning("Limite de débit proche (RateLimit-Remaining=%s) : pause de %.0f s",
                        self._restant, duree)
            ecoule = 0.0
            while ecoule < duree:
                tranche = min(1.0, duree - ecoule)
                self._sleep(tranche)
                ecoule += tranche
            with self._etat:
                # Pause bornée : si Reset était plus loin que la borne, on repart quand même
                # (sauf si une réponse arrivée entre-temps a fixé une échéance plus récente)
                if self._reprise == cible:
                    self._reprise = 0.0


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
        self.limiteur.attendre()
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
    adaptateur = _AdaptateurBsmb(limiteur, pool_connections=TAILLE_POOL, pool_maxsize=TAILLE_POOL,
                                 max_retries=retry)
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
