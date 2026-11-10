"""Read-only per-player status discovery and stable active-player selection."""

MPRIS_PATH = "/org/mpris/MediaPlayer2"
PROPERTIES = "org.freedesktop.DBus.Properties"


class PlayerFollower:
    def __init__(self):
        self.identities = {}
        self.previous_playing = set()

    def statuses(self, call, device_name, players):
        services = call(
            "/org/freedesktop/DBus",
            "org.freedesktop.DBus",
            "ListNames",
            destination="org.freedesktop.DBus",
        )[0]
        services = [s for s in services if s.startswith("org.mpris.MediaPlayer2.kdeconnect.")]
        self.identities = {k: v for k, v in self.identities.items() if k in services}
        matches = {f"{player} - {device_name}": player for player in players}
        result, duplicates = {}, set()
        for service in services:
            try:
                if service not in self.identities:
                    self.identities[service] = call(
                        MPRIS_PATH,
                        PROPERTIES,
                        "Get",
                        ("org.mpris.MediaPlayer2", "Identity"),
                        destination=service,
                    )[0]
                player = matches.get(self.identities[service])
                if not player:
                    continue
                if player in result:
                    duplicates.add(player)
                result[player] = call(
                    MPRIS_PATH,
                    PROPERTIES,
                    "Get",
                    ("org.mpris.MediaPlayer2.Player", "PlaybackStatus"),
                    destination=service,
                )[0]
            except RuntimeError:
                self.identities.pop(service, None)
        # Identically named phones/players are ambiguous: never guess a target.
        return {k: v for k, v in result.items() if k not in duplicates}

    def choose(self, current, statuses, locked=None):
        playing = {p for p, status in statuses.items() if status == "Playing"}
        newly_playing = playing - self.previous_playing
        self.previous_playing = playing
        if locked:
            return locked
        if len(newly_playing) == 1:
            return next(iter(newly_playing))
        if current in playing:
            return current
        if len(playing) == 1:
            return next(iter(playing))
        return current
