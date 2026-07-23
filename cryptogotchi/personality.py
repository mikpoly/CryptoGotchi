from __future__ import annotations

import hashlib
import math
import time
from collections import Counter
from typing import Any


STATE_LABELS = {
    "en": {
        "offline": "offline", "sleeping": "sleepy", "calm": "calm", "curious": "curious",
        "bullish": "hopeful", "bearish": "concerned", "panic": "on alert", "euphoric": "excited",
    },
    "fr": {
        "offline": "hors ligne", "sleeping": "veille calme", "calm": "calme", "curious": "curieux",
        "bullish": "optimiste", "bearish": "inquiet", "panic": "en alerte", "euphoric": "surexcité",
    },
}
STATE_LABELS_FR = STATE_LABELS["fr"]

BASE_MESSAGES = {
    "en": {
        "offline": [
            "The market feed went quiet. I am searching for a route back.",
            "I lost the price stream, but I am keeping the last readings safe.",
            "Connection interrupted. My watch continues locally.",
            "No fresh prices yet. I will keep retrying without panicking.",
        ],
        "sleeping": [
            "The market is barely moving, so I am listening for smaller signals.",
            "Prices are breathing slowly. I am awake with one eye open.",
            "A quiet market still leaves footprints. I am watching them.",
            "Very little motion for now. I am conserving energy, not attention.",
        ],
        "calm": [
            "The watchlist is moving at a steady pace.",
            "No violent move is spreading through the tracked market.",
            "Prices are active without crossing my danger lines.",
            "The market rhythm is stable, so I am continuing the watch.",
        ],
        "curious": [
            "Activity is rising beneath the surface, and I am leaning closer.",
            "Volume is waking up before price has fully decided.",
            "The market has started speaking louder than a moment ago.",
            "I am detecting more agitation than usual in the watchlist.",
        ],
        "bullish": [
            "Buyers are gaining ground across the tracked assets.",
            "Green is spreading through the watchlist, though I remain factual.",
            "Several prices are advancing together instead of moving alone.",
            "A positive impulse is crossing the market I watch.",
        ],
        "bearish": [
            "Sellers are gaining ground, so I have tightened my watch.",
            "Red is spreading through the tracked assets.",
            "Several prices are retreating together rather than in isolation.",
            "Downward pressure is becoming more visible in the watchlist.",
        ],
        "panic": [
            "Several sharp drops are now outside the ordinary range.",
            "The market is nervous. I am prioritizing facts over noise.",
            "Selling pressure has accelerated across the tracked assets.",
            "Red alert: multiple movements have crossed unusual thresholds.",
        ],
        "euphoric": [
            "Several rapid rises are now outside the ordinary range.",
            "The market is rushing upward, and I am keeping a cool head.",
            "Green is spreading quickly across the watchlist.",
            "Buyers are pushing hard, so I am checking every threshold twice.",
        ],
    },
    "fr": {
        "offline": [
            "Le flux du marché s'est tu. Je cherche une route pour revenir.",
            "J'ai perdu les prix, mais je conserve les dernières lectures.",
            "Connexion interrompue. Ma veille continue localement.",
            "Aucun nouveau prix. Je réessaie sans céder à la panique.",
        ],
        "sleeping": [
            "Le marché bouge à peine, alors j'écoute les signaux plus discrets.",
            "Les cours respirent lentement. Je reste éveillé d'un œil.",
            "Même un marché calme laisse des traces. Je les observe.",
            "Très peu de mouvement. J'économise mon énergie, pas mon attention.",
        ],
        "calm": [
            "La liste de suivi garde un rythme régulier.",
            "Aucun mouvement violent ne se propage parmi les actifs suivis.",
            "Les prix bougent sans franchir mes lignes de danger.",
            "Le rythme du marché est stable, je poursuis ma veille.",
        ],
        "curious": [
            "L'activité monte sous la surface et je me penche sur les chiffres.",
            "Le volume se réveille avant que le prix ait vraiment choisi.",
            "Le marché commence à parler plus fort qu'il y a un instant.",
            "Je détecte plus d'agitation que d'habitude dans la liste.",
        ],
        "bullish": [
            "Les acheteurs gagnent du terrain parmi les actifs suivis.",
            "Le vert s'étend, mais je reste attaché aux faits.",
            "Plusieurs prix avancent ensemble au lieu de bouger seuls.",
            "Une impulsion positive traverse le marché que je surveille.",
        ],
        "bearish": [
            "Les vendeurs gagnent du terrain, je resserre ma vigilance.",
            "Le rouge s'étend parmi les actifs suivis.",
            "Plusieurs prix reculent ensemble plutôt qu'en isolation.",
            "La pression baissière devient plus visible dans la liste.",
        ],
        "panic": [
            "Plusieurs chutes rapides sortent maintenant de l'ordinaire.",
            "Le marché devient nerveux. Je privilégie les faits au bruit.",
            "La pression vendeuse accélère sur les actifs suivis.",
            "Alerte rouge : plusieurs mouvements franchissent des seuils inhabituels.",
        ],
        "euphoric": [
            "Plusieurs hausses rapides sortent maintenant de l'ordinaire.",
            "Le marché fonce vers le haut et je garde la tête froide.",
            "Le vert s'étend rapidement dans la liste de suivi.",
            "Les acheteurs poussent fort, je vérifie chaque seuil deux fois.",
        ],
    },
}
BASE_MESSAGES_EN = BASE_MESSAGES["en"]
BASE_MESSAGES_FR = BASE_MESSAGES["fr"]

PROFILE_TONES = {
    "en": {
        "guardian": {
            "calm": "The perimeter is stable.", "curious": "I am verifying each signal before sounding an alarm.",
            "bullish": "I am watching the acceleration without being carried away.",
            "bearish": "I am reinforcing the watch around fragile zones.", "panic": "Sentinel mode is active.",
            "euphoric": "I am guarding against excess enthusiasm.", "offline": "I am protecting the last known state.",
            "sleeping": "Quiet watch mode is active.",
        },
        "explorer": {
            "calm": "The route is quiet, but the expedition continues.", "curious": "A trail is appearing inside the market noise.",
            "bullish": "The current is carrying the watchlist upward.", "bearish": "The terrain is becoming slippery.",
            "panic": "A storm has appeared on the map.", "euphoric": "The sky is bright, but I am checking the compass.",
            "offline": "The map is blank, so I am searching for a new signal.", "sleeping": "The expedition is resting at base camp.",
        },
        "sage": {
            "calm": "Calm also contains information.", "curious": "Volume sometimes arrives before movement.",
            "bullish": "A rise becomes meaningful only if it can persist.", "bearish": "A rapid fall deserves observation before reaction.",
            "panic": "Inside the noise, numbers remain our anchor.", "euphoric": "Euphoria is a signal, not a certainty.",
            "offline": "Absence of data is itself a condition to report.", "sleeping": "Stillness is not the same as emptiness.",
        },
    },
    "fr": {
        "guardian": {
            "calm": "Le périmètre reste stable.", "curious": "Je vérifie chaque signal avant de sonner l'alerte.",
            "bullish": "Je surveille l'accélération sans me laisser emporter.", "bearish": "Je renforce la veille autour des zones fragiles.",
            "panic": "Le mode sentinelle est activé.", "euphoric": "Je protège la veille contre l'excès d'enthousiasme.",
            "offline": "Je protège le dernier état connu.", "sleeping": "La garde silencieuse est active.",
        },
        "explorer": {
            "calm": "La route est tranquille, mais l'expédition continue.", "curious": "Une piste apparaît dans le bruit du marché.",
            "bullish": "Le courant porte la liste vers le haut.", "bearish": "Le terrain devient glissant.",
            "panic": "Une tempête apparaît sur la carte.", "euphoric": "Le ciel s'illumine, mais je vérifie la boussole.",
            "offline": "La carte est vide, je cherche un nouveau signal.", "sleeping": "L'expédition se repose au camp de base.",
        },
        "sage": {
            "calm": "Le calme contient lui aussi de l'information.", "curious": "Le volume précède parfois le mouvement.",
            "bullish": "Une hausse ne devient solide que si elle peut durer.", "bearish": "Une chute rapide mérite observation avant réaction.",
            "panic": "Dans le bruit, les chiffres restent notre ancre.", "euphoric": "L'euphorie est un signal, pas une certitude.",
            "offline": "L'absence de données est déjà un état à signaler.", "sleeping": "L'immobilité n'est pas le vide.",
        },
    },
}

HUMOR_LINES = {
    "en": {
        "sleeping": "Even the candles seem to be whispering.", "calm": "My alarm bell is enjoying a rare coffee break.",
        "curious": "My digital eyebrows just moved.", "bullish": "The green pixels are getting confident.",
        "bearish": "The red pixels have entered the room.", "panic": "This is not the moment for dramatic confetti.",
        "euphoric": "The rocket icon is asking for permission to launch.", "offline": "I cannot read minds, especially without packets.",
    },
    "fr": {
        "sleeping": "Même les bougies semblent chuchoter.", "calm": "Ma cloche d'alarme profite d'une rare pause café.",
        "curious": "Mes sourcils numériques viennent de bouger.", "bullish": "Les pixels verts prennent confiance.",
        "bearish": "Les pixels rouges viennent d'entrer dans la pièce.", "panic": "Ce n'est pas le moment de sortir les confettis dramatiques.",
        "euphoric": "L'icône fusée demande l'autorisation de décoller.", "offline": "Je ne lis pas dans les pensées, encore moins sans paquets réseau.",
    },
}

ACHIEVEMENTS = {
    "first_watch": {"icon": "👁", "en": "First Watch", "fr": "Première veille", "description_en": "Complete the first market observation.", "description_fr": "Terminer la première observation du marché."},
    "hundred_eyes": {"icon": "💯", "en": "Hundred Eyes", "fr": "Cent regards", "description_en": "Complete 100 observations.", "description_fr": "Terminer 100 observations."},
    "thousand_watch": {"icon": "🔭", "en": "Deep Watch", "fr": "Veille profonde", "description_en": "Complete 1,000 observations.", "description_fr": "Terminer 1 000 observations."},
    "first_alert": {"icon": "🔔", "en": "Signal Found", "fr": "Signal trouvé", "description_en": "Record the first threshold alert.", "description_fr": "Enregistrer la première alerte de seuil."},
    "storm_watcher": {"icon": "🛡", "en": "Storm Watcher", "fr": "Veilleur de tempête", "description_en": "Observe a panic market state.", "description_fr": "Observer un état de panique du marché."},
    "green_wave": {"icon": "🚀", "en": "Green Wave", "fr": "Vague verte", "description_en": "Observe an euphoric market state.", "description_fr": "Observer un état euphorique du marché."},
    "week_alive": {"icon": "📅", "en": "One Week Together", "fr": "Une semaine ensemble", "description_en": "Keep the companion for seven days.", "description_fr": "Garder le compagnon pendant sept jours."},
    "streak_7": {"icon": "🔥", "en": "Seven-Day Streak", "fr": "Série de sept jours", "description_en": "Observe markets on seven consecutive days.", "description_fr": "Observer le marché sept jours consécutifs."},
    "level_5": {"icon": "⭐", "en": "Seasoned Observer", "fr": "Observateur confirmé", "description_en": "Reach level 5.", "description_fr": "Atteindre le niveau 5."},
    "level_10": {"icon": "👑", "en": "Market Sage", "fr": "Sage du marché", "description_en": "Reach level 10.", "description_fr": "Atteindre le niveau 10."},
    "bond_50": {"icon": "💙", "en": "Trusted Companion", "fr": "Compagnon de confiance", "description_en": "Reach 50 bond points.", "description_fr": "Atteindre 50 points de lien."},
    "five_coins": {"icon": "🧭", "en": "Wide Horizon", "fr": "Large horizon", "description_en": "Track at least five cryptos.", "description_fr": "Surveiller au moins cinq cryptos."},
    "traveler": {"icon": "📡", "en": "Pocket Traveler", "fr": "Voyageur de poche", "description_en": "Observe the market over Bluetooth tethering.", "description_fr": "Observer le marché via partage Bluetooth."},
}


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, float(value)))


def choose_state(changes: list[float], volume_ratios: list[float] | None = None, online: bool = True) -> str:
    if not online:
        return "offline"
    clean = [float(x) for x in changes if x is not None and math.isfinite(float(x))]
    if not clean:
        return "sleeping"
    average = sum(clean) / len(clean)
    worst = min(clean)
    best = max(clean)
    negative_count = sum(1 for x in clean if x <= -3)
    positive_count = sum(1 for x in clean if x >= 3)
    broad_negative = negative_count >= max(2, (len(clean) + 1) // 2)
    broad_positive = positive_count >= max(2, (len(clean) + 1) // 2)
    if broad_negative or worst <= -7:
        return "panic"
    if broad_positive or best >= 7:
        return "euphoric"
    if average >= 1.5:
        return "bullish"
    if average <= -1.5:
        return "bearish"
    if volume_ratios and max(volume_ratios, default=0) >= 2:
        return "curious"
    if max(abs(x) for x in clean) < 0.25:
        return "sleeping"
    return "calm"


def _stable_choice(choices: list[str], seed: str, previous: str | None = None) -> str:
    filtered = [choice for choice in choices if choice != previous] or choices
    digest = hashlib.sha256(seed.encode("utf-8")).digest()
    return filtered[int.from_bytes(digest[:4], "big") % len(filtered)]


def state_message(state: str, language: str = "en", previous: str | None = None) -> str:
    language = "fr" if language == "fr" else "en"
    catalog = BASE_MESSAGES[language]
    choices = list(catalog.get(state, catalog["calm"]))
    seed = f"{state}:{int(time.time()) // 60}:{previous or ''}:{language}"
    return _stable_choice(choices, seed, previous)


def _ranked_moves(evaluated: list[dict[str, Any]]) -> list[tuple[float, str, float]]:
    ranked: list[tuple[float, str, float]] = []
    for item in evaluated:
        coin = item.get("coin", {})
        market = item.get("market", {})
        if not coin.get("include_in_market_mood", True) or market.get("is_stale") or market.get("market_status") == "closed":
            continue
        metrics = item.get("metrics", {})
        change = metrics.get("15m")
        if change is None:
            change = metrics.get("24h")
        if change is None:
            change = item.get("market", {}).get("change_24h")
        if change is None:
            continue
        symbol = str(coin.get("symbol", item.get("market", {}).get("symbol", coin.get("id", "?")))).upper()
        ranked.append((abs(float(change)), symbol, float(change)))
    return sorted(ranked, reverse=True)


def contextual_message(state: str, evaluated: list[dict[str, Any]], language: str = "en", previous: str | None = None) -> str:
    language = "fr" if language == "fr" else "en"
    base = state_message(state, language, previous)
    ranked = _ranked_moves(evaluated)
    if not ranked:
        return base
    _, symbol, change = ranked[0]
    if language == "fr":
        if state in {"bullish", "euphoric"} and change > 0:
            return f"{base} {symbol} mène le mouvement à {change:+.2f} %."
        if state in {"bearish", "panic"} and change < 0:
            return f"{base} {symbol} recule le plus à {change:.2f} %."
        if state == "curious":
            return f"{base} Je garde aussi un œil sur {symbol}."
    else:
        if state in {"bullish", "euphoric"} and change > 0:
            return f"{base} {symbol} leads the move at {change:+.2f}%."
        if state in {"bearish", "panic"} and change < 0:
            return f"{base} {symbol} is the weakest at {change:.2f}%."
        if state == "curious":
            return f"{base} I am also watching {symbol}."
    return base


class MicroBrain:
    """Persistent local companion brain designed for a Pi Zero 2 W.

    It combines deterministic market context, configurable personality traits,
    life statistics, achievements, interaction memory and daily journals. It is
    not a price predictor and never creates trade orders.
    """

    def __init__(self, db: Any):
        self.db = db
        saved = db.get_state("companion_brain_v2", {}) if db else {}
        legacy = db.get_state("companion_brain", {}) if db and not saved else {}
        self.memory: dict[str, Any] = saved if isinstance(saved, dict) else {}
        if not self.memory and isinstance(legacy, dict):
            self.memory.update(legacy)
        now = int(time.time())
        defaults = {
            "created_ts": now,
            "xp": 0,
            "observations": 0,
            "total_alerts": 0,
            "state": "offline",
            "state_streak": 0,
            "recent": [],
            "energy": 78.0,
            "stress": 18.0,
            "confidence": 50.0,
            "curiosity": 55.0,
            "bond": 10.0,
            "interactions": 0,
            "active_streak": 1,
            "last_observation_day": "",
            "state_counts": {},
            "achievements": [],
            "last_achievement": None,
            "daily": {},
            "last_interaction_ts": 0,
        }
        for key, value in defaults.items():
            self.memory.setdefault(key, value)
        self._persist()

    def _persist(self) -> None:
        if self.db:
            self.db.set_state("companion_brain_v2", self.memory)

    @staticmethod
    def _leader(evaluated: list[dict[str, Any]]) -> tuple[str | None, float | None]:
        ranked = _ranked_moves(evaluated)
        if not ranked:
            return None, None
        _, symbol, change = ranked[0]
        return symbol, change

    @staticmethod
    def _volume_star(evaluated: list[dict[str, Any]]) -> tuple[str | None, float | None]:
        best: tuple[float, str] | None = None
        for item in evaluated:
            coin = item.get("coin", {})
            market = item.get("market", {})
            if not coin.get("include_in_market_mood", True) or market.get("is_stale") or market.get("market_status") == "closed":
                continue
            ratio = item.get("metrics", {}).get("volume_ratio")
            if ratio is None:
                continue
            symbol = str(item.get("coin", {}).get("symbol", "?")).upper()
            candidate = (float(ratio), symbol)
            if best is None or candidate[0] > best[0]:
                best = candidate
        return (best[1], best[0]) if best else (None, None)

    @staticmethod
    def _day(now: int) -> str:
        return time.strftime("%Y-%m-%d", time.localtime(now))

    @staticmethod
    def _yesterday(day: str) -> str:
        parsed = time.mktime(time.strptime(day, "%Y-%m-%d"))
        return time.strftime("%Y-%m-%d", time.localtime(parsed - 86400))

    def _roll_day(self, now: int, language: str, name: str = "CryptoGotchi") -> None:
        today = self._day(now)
        daily = self.memory.get("daily")
        if not isinstance(daily, dict) or not daily.get("day"):
            self.memory["daily"] = {
                "day": today, "observations": 0, "alerts": 0, "max_move": 0.0,
                "leader_counts": {}, "state_counts": {}, "first_ts": now, "last_ts": now,
            }
            return
        if daily.get("day") == today:
            return
        text = self._journal_text(daily, language, name)
        if self.db and int(daily.get("observations", 0)) > 0:
            self.db.add_journal_entry(str(daily.get("day")), language, text, daily)
        self.memory["daily"] = {
            "day": today, "observations": 0, "alerts": 0, "max_move": 0.0,
            "leader_counts": {}, "state_counts": {}, "first_ts": now, "last_ts": now,
        }

    @staticmethod
    def _journal_text(daily: dict[str, Any], language: str, name: str) -> str:
        states = Counter(daily.get("state_counts") or {})
        dominant = states.most_common(1)[0][0] if states else "calm"
        leaders = Counter(daily.get("leader_counts") or {})
        leader = leaders.most_common(1)[0][0] if leaders else None
        observations = int(daily.get("observations", 0))
        alerts = int(daily.get("alerts", 0))
        max_move = float(daily.get("max_move", 0.0))
        mood = STATE_LABELS["fr" if language == "fr" else "en"].get(dominant, dominant)
        if language == "fr":
            leader_text = f" {leader} a le plus souvent dirigé mes observations." if leader else ""
            return (
                f"Journal de {name} : {observations} observations, {alerts} alertes, humeur dominante {mood}. "
                f"Le plus grand mouvement absolu a été de {max_move:.2f} %.{leader_text}"
            )
        leader_text = f" {leader} led my observations most often." if leader else ""
        return (
            f"{name} journal: {observations} observations, {alerts} alerts, dominant mood {mood}. "
            f"The largest absolute move was {max_move:.2f}%.{leader_text}"
        )

    def _update_daily(self, now: int, state: str, leader: str | None, leader_change: float | None, alerts: int) -> None:
        daily = self.memory.setdefault("daily", {})
        daily["observations"] = int(daily.get("observations", 0)) + 1
        daily["alerts"] = int(daily.get("alerts", 0)) + max(0, int(alerts))
        daily["last_ts"] = now
        daily["max_move"] = max(float(daily.get("max_move", 0.0)), abs(float(leader_change or 0.0)))
        state_counts = dict(daily.get("state_counts") or {})
        state_counts[state] = int(state_counts.get(state, 0)) + 1
        daily["state_counts"] = state_counts
        if leader:
            leader_counts = dict(daily.get("leader_counts") or {})
            leader_counts[leader] = int(leader_counts.get(leader, 0)) + 1
            daily["leader_counts"] = leader_counts

    def _update_life(self, state: str, alert_count: int, now: int) -> None:
        energy_delta = {
            "offline": -0.3, "sleeping": 0.8, "calm": 0.15, "curious": -0.25,
            "bullish": -0.35, "bearish": -0.45, "panic": -1.0, "euphoric": -0.8,
        }.get(state, 0.0)
        stress_target = {
            "offline": 45, "sleeping": 8, "calm": 18, "curious": 32,
            "bullish": 30, "bearish": 52, "panic": 90, "euphoric": 64,
        }.get(state, 25)
        stress = float(self.memory.get("stress", 18.0))
        self.memory["energy"] = _clamp(float(self.memory.get("energy", 78.0)) + energy_delta)
        self.memory["stress"] = _clamp(stress + (stress_target - stress) * 0.12 + min(3, alert_count * 0.4))
        confidence = float(self.memory.get("confidence", 50.0))
        confidence += 0.18 if state != "offline" else -0.8
        confidence += min(0.5, alert_count * 0.08)
        self.memory["confidence"] = _clamp(confidence)
        curiosity = float(self.memory.get("curiosity", 55.0))
        curiosity += 0.45 if state == "curious" else 0.15 if state in {"panic", "euphoric"} else -0.03
        self.memory["curiosity"] = _clamp(curiosity)

        day = self._day(now)
        last_day = str(self.memory.get("last_observation_day", ""))
        if day != last_day:
            if last_day and last_day == self._yesterday(day):
                self.memory["active_streak"] = int(self.memory.get("active_streak", 1)) + 1
            elif last_day:
                self.memory["active_streak"] = 1
            self.memory["last_observation_day"] = day

    def _achievement_checks(self, state: str, level: int, coin_count: int, network_type: str) -> list[str]:
        checks = {
            "first_watch": int(self.memory.get("observations", 0)) >= 1,
            "hundred_eyes": int(self.memory.get("observations", 0)) >= 100,
            "thousand_watch": int(self.memory.get("observations", 0)) >= 1000,
            "first_alert": int(self.memory.get("total_alerts", 0)) >= 1,
            "storm_watcher": int((self.memory.get("state_counts") or {}).get("panic", 0)) >= 1,
            "green_wave": int((self.memory.get("state_counts") or {}).get("euphoric", 0)) >= 1,
            "week_alive": self.age_days() >= 7,
            "streak_7": int(self.memory.get("active_streak", 1)) >= 7,
            "level_5": level >= 5,
            "level_10": level >= 10,
            "bond_50": float(self.memory.get("bond", 0)) >= 50,
            "five_coins": coin_count >= 5,
            "traveler": network_type == "bluetooth",
        }
        unlocked = list(self.memory.get("achievements", []))
        new: list[str] = []
        for key, condition in checks.items():
            if condition and key not in unlocked:
                unlocked.append(key)
                new.append(key)
        self.memory["achievements"] = unlocked
        if new:
            self.memory["last_achievement"] = new[-1]
        return new

    def age_days(self, now: int | None = None) -> int:
        now = int(now or time.time())
        return max(0, (now - int(self.memory.get("created_ts", now))) // 86400)

    @staticmethod
    def level_for_xp(xp: int) -> int:
        return 1 + max(0, int(xp)) // 120

    @staticmethod
    def next_level_xp(level: int) -> int:
        return max(1, int(level)) * 120

    def _accessory(self, configured: str = "auto") -> str:
        allowed = {"none", "glasses", "cap", "shield", "crown", "antenna"}
        if configured in allowed and configured != "auto":
            return configured
        achievements = set(self.memory.get("achievements", []))
        level = self.level_for_xp(int(self.memory.get("xp", 0)))
        if "level_10" in achievements:
            return "crown"
        if "storm_watcher" in achievements:
            return "shield"
        if level >= 7:
            return "antenna"
        if level >= 5:
            return "cap"
        if level >= 3:
            return "glasses"
        return "none"

    def _compose_local(
        self,
        state: str,
        evaluated: list[dict[str, Any]],
        language: str,
        previous: str | None,
        personality: dict[str, Any],
        now: int,
        streak: int,
    ) -> tuple[str, str, str | None, float | None]:
        language = "fr" if language == "fr" else "en"
        profile = str(personality.get("profile", "sage"))
        if profile not in {"sage", "guardian", "explorer"}:
            profile = "sage"
        leader, leader_change = self._leader(evaluated)
        volume_symbol, volume_ratio = self._volume_star(evaluated)
        base = state_message(state, language, previous)
        tone = PROFILE_TONES[language][profile].get(state, "")
        technical = int(personality.get("technical_level", 55))
        humor = int(personality.get("humor", 25))
        verbosity = int(personality.get("verbosity", 45))
        optimism = int(personality.get("optimism", 50))
        prudence = int(personality.get("prudence", 80))
        energy_style = int(personality.get("energy", 55))
        talk_frequency = int(personality.get("talk_frequency", 55))
        details: list[str] = []
        if leader and leader_change is not None:
            if language == "fr":
                details.append(f"{leader} {'avance' if leader_change >= 0 else 'recule'} de {abs(leader_change):.2f} %")
            else:
                details.append(f"{leader} {'advances' if leader_change >= 0 else 'retreats'} {abs(leader_change):.2f}%")
        if volume_symbol and volume_ratio is not None and volume_ratio >= 1.5:
            details.append((f"volume ×{volume_ratio:.1f} sur {volume_symbol}" if language == "fr" else f"{volume_symbol} volume ×{volume_ratio:.1f}"))
        detail = " · ".join(details[:2])
        hour = time.localtime(now).tm_hour
        period = (
            ("nuit" if hour < 6 else "matin" if hour < 12 else "après-midi" if hour < 18 else "soir")
            if language == "fr" else
            ("night" if hour < 6 else "morning" if hour < 12 else "afternoon" if hour < 18 else "evening")
        )
        candidates = [base]
        if talk_frequency >= 25:
            candidates.extend([f"{base} {tone}", f"{tone} {base}"])
        if verbosity >= 35 and talk_frequency >= 35:
            prefix = f"Veille du {period} : " if language == "fr" else f"{period.capitalize()} watch: "
            candidates.append(prefix + base)
        if detail and technical >= 35 and talk_frequency >= 30:
            candidates.append((f"{tone} Je note : {detail}." if language == "fr" else f"{tone} My note: {detail}."))
        if prudence >= 70 and state in {"bullish", "euphoric"}:
            candidates.append(base + (" Je garde une marge de prudence tant que le mouvement n'est pas confirmé." if language == "fr" else " I keep a margin of caution until the move proves durable."))
        elif prudence <= 30 and state in {"curious", "bullish"}:
            candidates.append(base + (" J'explore ce mouvement de plus près." if language == "fr" else " I am leaning into this trail for a closer look."))
        if energy_style >= 75 and state in {"curious", "bullish", "euphoric"}:
            candidates.append((base.rstrip(".") + "!") + (" Mes capteurs sont pleinement éveillés." if language == "fr" else " My sensors are fully awake."))
        elif energy_style <= 25:
            candidates.append(base + (" Je reste en mode basse énergie." if language == "fr" else " I am staying in low-energy watch mode."))
        if humor >= 60:
            candidates.append(f"{base} {HUMOR_LINES[language].get(state, '')}")
        if optimism >= 75 and state in {"bearish", "panic", "offline"}:
            candidates.append(base + (" Je reste patient : un état n'est pas une destinée." if language == "fr" else " I remain patient: a state is not a destiny."))
        if optimism <= 25 and state in {"bullish", "euphoric"}:
            candidates.append(base + (" Je refuse de confondre élan et certitude." if language == "fr" else " I will not confuse momentum with certainty."))
        recent = list(self.memory.get("recent", []))[-10:]
        seed = f"{now // 60}:{state}:{leader}:{profile}:{streak}:{technical}:{humor}:{verbosity}:{prudence}:{energy_style}:{talk_frequency}"
        message = _stable_choice([x.strip() for x in candidates if x.strip()], seed, previous)
        if message in recent:
            message = f"{base} {detail}." if detail else f"{base} #{int(self.memory.get('observations', 0)) + 1}"
        if verbosity < 30 and len(message) > 150:
            message = message.split(". ", 1)[0].rstrip(".") + "."
        thought_map = {
            "en": {
                "offline": "Holding the last values while I search for a new route.",
                "sleeping": "Comparing micro-movements for the next wake-up.",
                "calm": "Measuring rhythm before judging direction.",
                "curious": "Cross-checking volume and velocity to separate signal from noise.",
                "bullish": "Checking whether the rise is broad or carried by one asset.",
                "bearish": "Checking whether the decline is spreading or isolated.",
                "panic": "Prioritizing factual alerts and suppressing repetition.",
                "euphoric": "Watching for reversals after acceleration.",
            },
            "fr": {
                "offline": "Je conserve les dernières valeurs et cherche une nouvelle route.",
                "sleeping": "Je compare les micro-variations pour repérer le prochain réveil.",
                "calm": "Je mesure le rythme avant de juger la direction.",
                "curious": "Je croise volume et vitesse pour distinguer le signal du bruit.",
                "bullish": "Je vérifie si la hausse est large ou portée par un seul actif.",
                "bearish": "Je vérifie si la baisse s'étend ou reste isolée.",
                "panic": "Je privilégie les alertes factuelles et bloque les répétitions.",
                "euphoric": "Je surveille les retournements après l'accélération.",
            },
        }
        return message, thought_map[language].get(state, ""), leader, leader_change

    def observe(
        self,
        state: str,
        evaluated: list[dict[str, Any]],
        language: str = "en",
        previous: str | None = None,
        profile: str = "sage",
        now: int | None = None,
        alert_count: int = 0,
        personality: dict[str, Any] | None = None,
        coin_count: int | None = None,
        network_type: str = "unknown",
        name: str = "CryptoGotchi",
    ) -> dict[str, Any]:
        now = int(now or time.time())
        language = "fr" if language == "fr" else "en"
        personality = dict(personality or {})
        personality.setdefault("profile", profile)
        self._roll_day(now, language, name)
        old_state = str(self.memory.get("state", "offline"))
        state_streak = int(self.memory.get("state_streak", self.memory.get("streak", 0))) + 1 if old_state == state else 1
        observations = int(self.memory.get("observations", 0)) + 1
        xp = int(self.memory.get("xp", 0)) + 1 + min(12, max(0, alert_count) * 3) + (2 if old_state != state else 0)
        total_alerts = int(self.memory.get("total_alerts", 0)) + max(0, alert_count)
        level = self.level_for_xp(xp)
        self._update_life(state, alert_count, now)
        message, thought, leader, leader_change = self._compose_local(
            state, evaluated, language, previous, personality, now, state_streak
        )
        self.memory.update({
            "xp": xp,
            "observations": observations,
            "total_alerts": total_alerts,
            "state": state,
            "state_streak": state_streak,
            "profile": personality.get("profile", "sage"),
            "recent": (list(self.memory.get("recent", [])) + [message])[-12:],
            "last_ts": now,
        })
        state_counts = dict(self.memory.get("state_counts") or {})
        state_counts[state] = int(state_counts.get(state, 0)) + 1
        self.memory["state_counts"] = state_counts
        self._update_daily(now, state, leader, leader_change, alert_count)
        new_achievements = self._achievement_checks(state, level, coin_count or len(evaluated), network_type)
        accessory = self._accessory(str(personality.get("accessory", "auto")))
        self._persist()
        achievement_payload = self.achievement_details(language, only=new_achievements)
        return {
            "engine": "micro-brain-v2",
            "is_llm": False,
            "profile": personality.get("profile", "sage"),
            "level": level,
            "xp": xp,
            "next_level_xp": self.next_level_xp(level),
            "observations": observations,
            "state_streak": state_streak,
            "mood": STATE_LABELS[language].get(state, state),
            "thought": thought,
            "message": message,
            "leader": leader,
            "leader_change": leader_change,
            "energy": round(float(self.memory.get("energy", 0)), 1),
            "stress": round(float(self.memory.get("stress", 0)), 1),
            "confidence": round(float(self.memory.get("confidence", 0)), 1),
            "curiosity": round(float(self.memory.get("curiosity", 0)), 1),
            "bond": round(float(self.memory.get("bond", 0)), 1),
            "age_days": self.age_days(now),
            "active_streak": int(self.memory.get("active_streak", 1)),
            "interactions": int(self.memory.get("interactions", 0)),
            "accessory": accessory,
            "achievement_count": len(self.memory.get("achievements", [])),
            "new_achievement": achievement_payload[-1] if achievement_payload else None,
        }

    def interaction(self, action: str, language: str = "en", now: int | None = None) -> dict[str, Any]:
        now = int(now or time.time())
        language = "fr" if language == "fr" else "en"
        action = action if action in {"pet", "encourage", "rest"} else "pet"
        energy = float(self.memory.get("energy", 70))
        stress = float(self.memory.get("stress", 20))
        confidence = float(self.memory.get("confidence", 50))
        bond = float(self.memory.get("bond", 10))
        if action == "pet":
            bond += 2.5; stress -= 4; energy += 0.5
            text = "That felt good. I will keep watching with you." if language == "en" else "Ça fait du bien. Je continue de veiller avec toi."
        elif action == "encourage":
            bond += 1.5; confidence += 3; energy += 2
            text = "Signal received. My confidence circuits are brighter." if language == "en" else "Signal reçu. Mes circuits de confiance brillent davantage."
        else:
            bond += 0.5; stress -= 7; energy += 7
            text = "Quiet mode accepted. I will recover without stopping the watch." if language == "en" else "Mode calme accepté. Je récupère sans arrêter la veille."
        self.memory.update({
            "energy": _clamp(energy), "stress": _clamp(stress), "confidence": _clamp(confidence),
            "bond": _clamp(bond), "interactions": int(self.memory.get("interactions", 0)) + 1,
            "last_interaction_ts": now,
        })
        level = self.level_for_xp(int(self.memory.get("xp", 0)))
        new = self._achievement_checks(str(self.memory.get("state", "calm")), level, 0, "unknown")
        self._persist()
        return {
            "action": action,
            "message": text,
            "energy": round(self.memory["energy"], 1),
            "stress": round(self.memory["stress"], 1),
            "confidence": round(self.memory["confidence"], 1),
            "bond": round(self.memory["bond"], 1),
            "new_achievement": (self.achievement_details(language, only=new)[-1] if new else None),
        }

    @staticmethod
    def _coin_fact_line(coin: dict[str, Any], language: str) -> tuple[str, float | None]:
        symbol = str(coin.get("symbol", coin.get("id", "?"))).upper()
        metrics = coin.get("metrics", {}) or {}
        values = [("15m", metrics.get("15m")), ("1h", metrics.get("1h")), ("24h", coin.get("change_24h"))]
        parts = [f"{label} {float(value):+.2f}%" for label, value in values if value is not None]
        volume = metrics.get("volume_ratio")
        if volume is not None and float(volume) >= 1.5:
            parts.append(f"volume ×{float(volume):.1f}")
        facts = " · ".join(parts) or ("no reliable movement window yet" if language == "en" else "pas encore de fenêtre fiable")
        kind = str(coin.get("asset_kind", "crypto"))
        market_status = str(coin.get("market_status", "open"))
        if kind == "tokenized_asset":
            facts += (" · actif tokenisé, pas l’action officielle" if language == "fr" else " · tokenized asset, not the official share")
        elif kind == "crypto_token":
            facts += (" · jeton crypto, pas le métal spot" if language == "fr" else " · crypto token, not the spot metal")
        elif kind == "commodity":
            facts += ((" · session fermée" if market_status == "closed" else " · métal spot par once troy") if language == "fr" else (" · market session closed" if market_status == "closed" else " · spot metal per troy ounce"))
        comparable = metrics.get("15m")
        if comparable is None:
            comparable = metrics.get("1h")
        if comparable is None:
            comparable = coin.get("change_24h")
        return f"{symbol}: {facts}", float(comparable) if comparable is not None else None

    @staticmethod
    def ask_about_coins(coins: list[dict[str, Any]], language: str = "en", profile: str = "sage") -> str:
        language = "fr" if language == "fr" else "en"
        coins = [coin for coin in coins if isinstance(coin, dict)][:5]
        if not coins:
            return "I need fresh data for at least one selected asset first." if language == "en" else "J’ai d’abord besoin de données fraîches pour au moins un actif sélectionné."
        lines: list[str] = []
        ranked: list[tuple[float, str]] = []
        for coin in coins:
            line, move = MicroBrain._coin_fact_line(coin, language)
            lines.append(line)
            if move is not None:
                ranked.append((move, str(coin.get("symbol", coin.get("id", "?"))).upper()))
        if len(coins) == 1:
            ending = {
                "guardian": "Je garde les seuils actifs sans transformer cela en ordre de trading.",
                "explorer": "C’est une piste à observer, pas une prédiction.",
                "sage": "Ces chiffres décrivent le présent, pas le futur.",
            }.get(profile, "Ces chiffres décrivent le présent, pas le futur.") if language == "fr" else {
                "guardian": "I am keeping its thresholds active without turning that into a trade order.",
                "explorer": "It is a trail to observe, not a prediction.",
                "sage": "These numbers describe the present, not the future.",
            }.get(profile, "These numbers describe the present, not the future.")
            prefix = "Mon regard sur " if language == "fr" else "My view of "
            symbol = str(coins[0].get("symbol", "?")).upper()
            facts = lines[0].split(": ", 1)[1] if ": " in lines[0] else lines[0]
            return f"{prefix}{symbol} : {facts}. {ending}"

        comparison = "; ".join(lines)
        insight = ""
        if ranked:
            strongest = max(ranked)
            weakest = min(ranked)
            if strongest[1] == weakest[1]:
                insight = (" Les fenêtres comparables sont encore trop limitées pour les départager." if language == "fr" else " Comparable windows are still too limited to separate them.")
            else:
                insight = (
                    f" Sur la première fenêtre comparable disponible, {strongest[1]} est le plus fort ({strongest[0]:+.2f} %) et {weakest[1]} le plus faible ({weakest[0]:+.2f} %)."
                    if language == "fr" else
                    f" On the first comparable window available, {strongest[1]} is strongest ({strongest[0]:+.2f}%) and {weakest[1]} is weakest ({weakest[0]:+.2f}%)."
                )
        ending = (" Comparaison factuelle, pas une recommandation d’achat ou de vente." if language == "fr" else " This is a factual comparison, not a buy or sell recommendation.")
        prefix = "Comparaison des actifs sélectionnés — " if language == "fr" else "Selected asset comparison — "
        return prefix + comparison + "." + insight + ending

    @staticmethod
    def ask_about_coin(coin: dict[str, Any] | None, language: str = "en", profile: str = "sage") -> str:
        return MicroBrain.ask_about_coins([coin] if coin else [], language, profile)

    def snapshot(self, language: str = "en", personality: dict[str, Any] | None = None) -> dict[str, Any]:
        language = "fr" if language == "fr" else "en"
        xp = int(self.memory.get("xp", 0))
        level = self.level_for_xp(xp)
        personality = personality or {}
        return {
            "engine": "micro-brain-v2",
            "is_llm": False,
            "level": level,
            "xp": xp,
            "next_level_xp": self.next_level_xp(level),
            "observations": int(self.memory.get("observations", 0)),
            "mood": STATE_LABELS[language].get(str(self.memory.get("state", "offline")), str(self.memory.get("state", "offline"))),
            "energy": round(float(self.memory.get("energy", 0)), 1),
            "stress": round(float(self.memory.get("stress", 0)), 1),
            "confidence": round(float(self.memory.get("confidence", 0)), 1),
            "curiosity": round(float(self.memory.get("curiosity", 0)), 1),
            "bond": round(float(self.memory.get("bond", 0)), 1),
            "age_days": self.age_days(),
            "active_streak": int(self.memory.get("active_streak", 1)),
            "interactions": int(self.memory.get("interactions", 0)),
            "accessory": self._accessory(str(personality.get("accessory", "auto"))),
            "achievement_count": len(self.memory.get("achievements", [])),
        }

    def achievement_details(self, language: str = "en", only: list[str] | None = None) -> list[dict[str, Any]]:
        language = "fr" if language == "fr" else "en"
        unlocked = list(self.memory.get("achievements", []))
        keys = only if only is not None else list(ACHIEVEMENTS)
        result = []
        for key in keys:
            item = ACHIEVEMENTS.get(key)
            if not item:
                continue
            result.append({
                "key": key,
                "icon": item["icon"],
                "title": item[language],
                "description": item[f"description_{language}"],
                "unlocked": key in unlocked,
            })
        return result

    def journals(self, limit: int = 30) -> list[dict[str, Any]]:
        return self.db.latest_journal_entries(limit) if self.db else []

    def force_journal(self, language: str = "en", name: str = "CryptoGotchi", now: int | None = None) -> dict[str, Any] | None:
        now = int(now or time.time())
        daily = self.memory.get("daily") or {}
        if int(daily.get("observations", 0)) <= 0 or not self.db:
            return None
        text = self._journal_text(daily, language, name)
        self.db.add_journal_entry(str(daily.get("day", self._day(now))), language, text, daily)
        return self.db.latest_journal_entries(1)[0]

    def social_digest(self, state: str, evaluated: list[dict[str, Any]], name: str = "CryptoGotchi", language: str = "en") -> str:
        language = "fr" if language == "fr" else "en"
        ranked = _ranked_moves(evaluated)
        moves = [f"{symbol} {change:+.2f}%" for _, symbol, change in ranked[:3]]
        market = ", ".join(moves) if moves else ("marché sans mouvement net" if language == "fr" else "market without a clear move")
        mood = STATE_LABELS[language].get(state, state)
        if language == "fr":
            return f"📓 Journal de {name} — humeur : {mood}. Mouvements : {market}. Observation automatique, pas un conseil financier."
        return f"📓 {name} journal — mood: {mood}. Moves: {market}. Automated observation, not financial advice."
