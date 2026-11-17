# Setup: development and deployment

The dashboard runs as a Docker container on an always-on machine in the home network (here a
Raspberry Pi 3b) and is shown by a tablet in kiosk mode ([tablet setup](tablet.md)).
Development, tests and image builds happen on a workstation (here WSL; any Linux or macOS with
Docker should do), the Pi only runs the finished container.

## Prerequisites

- [uv](https://docs.astral.sh/uv/) (fetches Python 3.14 by itself)
- For deployment: Docker with `buildx` on the workstation, SSH access to the Pi

## Development

```sh
uv sync                                   # install dependencies
uv run playwright install chromium-headless-shell   # browser for the layout tests
cp config.example.yaml config.yaml        # local config, gitignored
uv run pytest                             # behaviour tests (live API tests: uv run pytest -m live)
uv run pytest --cov --cov-report=term-missing   # with coverage (lines and branches)
uv run ruff check && uv run ruff format --check
uv run home-dashboard serve --reload      # http://localhost:3274/
uv run home-dashboard find-stop "Marktplatz Halle"   # stop ids for config.yaml
uv run home-dashboard check-config        # validate config.yaml, prints a summary without secrets
uv run python scripts/screenshot.py       # regenerate docs/screenshot.png (made-up data)
```

The port is **3274** (T9 for "DASH"). CI runs lint and tests on every push
(`.github/workflows/ci.yml`) and keeps the coverage badge current via the `badges` branch; it
builds no image.

## Configuration

`config.yaml` is gitignored because it holds the secret iCal address of the calendar. Every option
is explained in [`config.example.yaml`](../config.example.yaml); see
[customizing](customizing.md) for adapting stops, people and location.

## Deployment (Raspberry Pi)

One-time setup on the Pi:

1. Install Docker and the compose plugin, add the user to the `docker` group
   (Debian trixie: `sudo apt install docker.io docker-compose && sudo usermod -aG docker $USER`, re-login).
2. SSH key login from the workstation: `ssh-copy-id pi@<pi-host>`.
3. Once on the workstation, if Docker cannot build arm64 images yet:
   `docker run --privileged --rm tonistiigi/binfmt --install arm64` (Docker Desktop can already).

Deploy (Docker running on the workstation):

```sh
scripts/deploy.sh pi@<pi-host>            # or: export DEPLOY_HOST=pi@<pi-host>; scripts/deploy.sh
```

The script

1. validates the local `config.yaml` (`home-dashboard check-config`), if there is one,
2. cross-builds the `linux/arm64` image and ships it via `docker save | ssh … docker load` (no registry),
3. uploads `config.yaml` (mode 600) to `~/home-dashboard/config.yaml` on the Pi; without a local
   `config.yaml` the one on the Pi is kept,
4. recreates the container with `docker compose` and waits for `http://<pi-host>:3274/healthz`.

After config-only changes simply run the script again. The container restarts on its own after a
reboot (`restart: unless-stopped`).

Another always-on machine works the same way; for an x86 host change `--platform` in
`scripts/deploy.sh`.
