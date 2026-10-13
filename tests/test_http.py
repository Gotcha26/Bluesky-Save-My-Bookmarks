"""Session HTTP partagée (core/http.py) : User-Agent, retries, limiteur de débit."""
import logging
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
import requests
from requests.adapters import HTTPAdapter

from core import http as bsmb_http
from core.version import __version__
from tests.conftest import GET_SESSION_REEL


def _reponse(statut=200, entetes=None, url="http://exemple.test/"):
    r = requests.Response()
    r.status_code = statut
    r._content = b"{}"
    r.headers.update(entetes or {})
    r.url = url
    return r


class AdaptateurFactice(bsmb_http._AdaptateurBsmb):
    """Adaptateur de BSMB (limiteur compris) dont l'envoi réel renvoie des réponses prédéfinies."""

    def __init__(self, limiteur, reponses):
        super().__init__(limiteur)
        self.reponses = list(reponses)
        self.appels = 0

    def _envoyer(self, request, **kwargs):
        self.appels += 1
        r = self.reponses.pop(0)
        r.request = request
        return r


class Horloge:
    """Horloge factice : sleep() la fait avancer."""

    def __init__(self, debut=1000.0):
        self.t = debut
        self.pauses = []

    def now(self):
        return self.t

    def sleep(self, s):
        self.pauses.append(s)
        self.t += s


def _session_factice(reponses, horloge=None, **kw):
    horloge = horloge or Horloge()
    limiteur = bsmb_http.RateLimiter(horloge=horloge.now, sleep=horloge.sleep, **kw)
    session = bsmb_http.build_session(limiteur)
    adaptateur = AdaptateurFactice(limiteur, reponses)
    session.mount("http://", adaptateur)
    return session, limiteur, adaptateur, horloge


# ---------------------------------------------------------------- session

def test_user_agent_identifie_bsmb():
    session = bsmb_http.build_session()
    assert session.headers["User-Agent"] == (
        f"BSMB/{__version__} (+https://github.com/Gotcha26/Bluesky-Save-My-Bookmarks)"
    )


def test_adaptateur_monte_avec_retry():
    session = bsmb_http.build_session()
    for prefixe in ("http://", "https://"):
        adaptateur = session.get_adapter(prefixe + "exemple.test")
        retry = adaptateur.max_retries
        assert retry.total == 4
        assert retry.backoff_factor == 1
        assert set(retry.status_forcelist) == {429, 500, 502, 503, 504}
        assert {"GET", "POST"} <= set(retry.allowed_methods)
        assert retry.respect_retry_after_header is True
        assert retry.raise_on_status is False
        assert adaptateur._pool_maxsize == 16


def test_retry_after_borne():
    retry = bsmb_http.build_session().get_adapter("https://x").max_retries

    class Rep:
        headers = {"Retry-After": "86400"}

    assert retry.get_retry_after(Rep()) == bsmb_http.ATTENTE_MAX


def test_get_session_est_un_singleton_partage():
    a = GET_SESSION_REEL()
    b = GET_SESSION_REEL()
    assert a is b
    assert isinstance(a, requests.Session)


def test_get_session_singleton_sous_concurrence(monkeypatch):
    # Repart d'un singleton vide, sinon la course à la création n'est pas exercée
    monkeypatch.setattr(bsmb_http, "_session", None)
    vues = []
    barriere = threading.Barrier(6)

    def travail():
        barriere.wait()
        vues.append(GET_SESSION_REEL())

    fils = [threading.Thread(target=travail) for _ in range(6)]
    for f in fils:
        f.start()
    for f in fils:
        f.join()
    assert len({id(s) for s in vues}) == 1


# ---------------------------------------------------------------- retries

class _Serveur(BaseHTTPRequestHandler):
    sequence = []
    vus = []

    def do_GET(self):
        type(self).vus.append(self.headers.get("User-Agent"))
        statut = type(self).sequence.pop(0)
        corps = b'{"ok": true}'
        self.send_response(statut)
        self.send_header("Content-Length", str(len(corps)))
        self.end_headers()
        self.wfile.write(corps)

    def log_message(self, *args):
        pass


@pytest.fixture
def serveur_local():
    """Serveur HTTP sur la boucle locale (aucun accès Internet)."""
    _Serveur.sequence = []
    _Serveur.vus = []
    srv = HTTPServer(("127.0.0.1", 0), _Serveur)
    fil = threading.Thread(target=srv.serve_forever, daemon=True)
    fil.start()
    yield srv, _Serveur
    srv.shutdown()
    srv.server_close()


def test_retry_sur_503_puis_200(serveur_local):
    srv, etat = serveur_local
    etat.sequence = [503, 200]
    session = bsmb_http.build_session()
    session.trust_env = False
    r = session.get(f"http://127.0.0.1:{srv.server_port}/x", timeout=5)
    assert r.status_code == 200
    assert etat.sequence == []
    assert etat.vus[0].startswith("BSMB/")


def test_429_final_est_rendu_sans_exception(serveur_local):
    srv, etat = serveur_local
    etat.sequence = [429] * 5
    session = bsmb_http.build_session()
    session.trust_env = False
    # backoff nul pour ne pas ralentir le test
    session.get_adapter("http://").max_retries.backoff_factor = 0
    r = session.get(f"http://127.0.0.1:{srv.server_port}/x", timeout=5)
    assert r.status_code == 429
    assert etat.sequence == []  # 1 appel + 4 reprises


# ---------------------------------------------------------------- limiteur

def test_pause_quand_remaining_sous_le_seuil(caplog):
    horloge = Horloge()
    entetes = {"RateLimit-Remaining": "10", "RateLimit-Reset": str(int(horloge.t) + 5)}
    session, limiteur, adaptateur, horloge = _session_factice(
        [_reponse(200, entetes), _reponse(200)], horloge)
    with caplog.at_level(logging.INFO, logger="bsmb.http"):
        session.get("http://exemple.test/a")
        assert horloge.pauses == []  # rien à attendre avant la première réponse
        session.get("http://exemple.test/b")
    assert sum(horloge.pauses) == pytest.approx(5)
    assert all(p <= 1 for p in horloge.pauses)
    assert len([m for m in caplog.messages if "pause" in m.lower()]) == 1


def test_pas_de_pause_au_dessus_du_seuil():
    horloge = Horloge()
    entetes = {"RateLimit-Remaining": "500", "RateLimit-Reset": str(int(horloge.t) + 60)}
    session, _, _, horloge = _session_factice([_reponse(200, entetes), _reponse(200)], horloge)
    session.get("http://exemple.test/a")
    session.get("http://exemple.test/b")
    assert horloge.pauses == []


def test_pause_bornee():
    horloge = Horloge()
    entetes = {"RateLimit-Remaining": "0", "RateLimit-Reset": str(int(horloge.t) + 99999)}
    session, _, _, horloge = _session_factice([_reponse(200, entetes), _reponse(200)], horloge)
    session.get("http://exemple.test/a")
    session.get("http://exemple.test/b")
    assert sum(horloge.pauses) == pytest.approx(bsmb_http.ATTENTE_MAX)


def test_entetes_absents_ou_invalides_ignores():
    horloge = Horloge()
    session, _, _, horloge = _session_factice([
        _reponse(200, {"RateLimit-Remaining": "abc", "RateLimit-Reset": "x"}),
        _reponse(200, {"RateLimit-Remaining": "3"}),
        _reponse(200),
    ], horloge)
    for _ in range(3):
        session.get("http://exemple.test/")
    assert horloge.pauses == []


def test_reset_deja_passe_aucune_pause():
    horloge = Horloge()
    entetes = {"RateLimit-Remaining": "1", "RateLimit-Reset": str(int(horloge.t) - 10)}
    session, _, _, horloge = _session_factice([_reponse(200, entetes), _reponse(200)], horloge)
    session.get("http://exemple.test/a")
    session.get("http://exemple.test/b")
    assert horloge.pauses == []


def test_le_semaphore_borne_la_concurrence(monkeypatch):
    actifs = []
    maxi = []
    verrou = threading.Lock()

    def faux_send(self, request, **kwargs):
        with verrou:
            actifs.append(1)
            maxi.append(len(actifs))
        time.sleep(0.03)
        with verrou:
            actifs.pop()
        return _reponse(200)

    monkeypatch.setattr(bsmb_http._AdaptateurBsmb, "_envoyer", faux_send)
    limiteur = bsmb_http.RateLimiter(max_simultanes=2)
    session = bsmb_http.build_session(limiteur)
    fils = [threading.Thread(target=session.get, args=("http://exemple.test/",)) for _ in range(8)]
    for f in fils:
        f.start()
    for f in fils:
        f.join()
    assert max(maxi) == 2


class _Redirection(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/a":
            self.send_response(302)
            self.send_header("Location", "/b")
            self.send_header("Content-Length", "0")
            self.end_headers()
        else:
            corps = b"fin"
            self.send_response(200)
            self.send_header("Content-Length", str(len(corps)))
            self.end_headers()
            self.wfile.write(corps)

    def log_message(self, *args):
        pass


def test_redirection_avec_un_seul_creneau_ne_bloque_pas():
    """Régression : chaque saut de redirection prend puis rend son créneau (pas d'interblocage)."""
    srv = HTTPServer(("127.0.0.1", 0), _Redirection)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        session = bsmb_http.build_session(bsmb_http.RateLimiter(max_simultanes=1))
        session.trust_env = False
        resultat = []
        fil = threading.Thread(
            target=lambda: resultat.append(session.get(f"http://127.0.0.1:{srv.server_port}/a", timeout=5)),
            daemon=True)
        fil.start()
        fil.join(timeout=10)
        assert not fil.is_alive(), "interblocage : le créneau est retenu pendant la redirection"
        assert resultat[0].status_code == 200 and resultat[0].text == "fin"
        assert len(resultat[0].history) == 1
    finally:
        srv.shutdown()
        srv.server_close()


def test_limiteur_par_defaut():
    limiteur = bsmb_http.RateLimiter()
    assert limiteur.seuil == 50
    assert limiteur.max_simultanes == 8
    assert bsmb_http.ATTENTE_MAX == 300
