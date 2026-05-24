# Troubleshooting

Siehe README und zukünftige Detaildokumentation.


---

# Neue typische Probleme

## AP4: Linux-venv kann nicht erstellt werden

Symptom:

```text
ensurepip is not available
apt install python3.14-venv
```

Ursache: Die Linux-Installation hat Python, aber nicht das passende venv-/pip-Paket.

Behebung:

```bash
sudo apt update
sudo apt install -y python3-venv python3-pip
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m pip check
```

Wenn vorher eine kaputte `.venv` oder `.venv-linux` erzeugt wurde, diese vorher entfernen:

```bash
rm -rf .venv .venv-linux
```

## AP4: Docker API nicht erreichbar

Symptom:

```text
permission denied while trying to connect to the docker API at unix:///var/run/docker.sock
```

Pruefen:

```bash
id
ls -l /var/run/docker.sock
docker compose ps
```

Behebung auf normalen Linux-Installationen:

```bash
sudo usermod -aG docker "$USER"
newgrp docker
docker compose ps
```

Falls der Docker-Socket ungewoehnlich auf `nobody:nogroup` liegt oder die
Session trotz passender Gruppe keinen Zugriff bekommt, die Shell neu starten
oder den Host-Docker-Dienst bzw. die WSL-/VM-Integration korrigieren. Erst wenn
`docker compose ps` ohne `sudo` funktioniert, AP4 fortsetzen.

## AP4: pip kann Requirements nicht installieren

Symptom:

```text
Failed to establish a new connection: [Errno -2] Name or service not known
No matching distribution found for yfinance
```

Wenn diese Meldung direkt nach mehreren PyPI-Retries kommt, ist das in der
Regel kein Paketversionsproblem, sondern DNS-/Netzwerkzugriff.

Pruefen:

```bash
.venv/bin/python -m pip install -r requirements.txt
```

Erst fortsetzen, wenn pip PyPI erreichen kann oder ein interner Package-Index
konfiguriert ist.

## Portfolio bleibt unter Zielgröße

Prüfen:

```bash
qs --details
```

Auf folgende Werte achten:

```text
Fehlende Real-Positionen
Effektives Trade-Limit
```

---

## BUY nicht ausführbar

Mögliche Ursache:

```text
max_funding_sell_pct zu niedrig
```

Anpassen:

```bash
docker compose run --rm app python -m cli.update_settings   --max-funding-sell-pct 0.25
```

---

## Settings geändert aber keine Wirkung

Settings wirken nur auf zukünftige Monatsläufe.

Historische Snapshots bleiben eingefroren.
