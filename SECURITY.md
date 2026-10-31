# Security

runboard is a dashboard you run on your own computer. It starts training commands, reads and writes files in your
project folders and holds a Kaggle token, so access to it is access to your machine. This page says how that access is
limited and what is outside its scope.

## Who can use the dashboard

| Who | How | Can do |
|---|---|---|
| This computer | Any loopback connection (`localhost`, `127.0.0.1`), no login | Everything |
| A paired device | Only while **Tablet access** is on; pairs once with a one-time QR link or 6-digit code | Follow runs, start and stop them, add extra runs, run project jobs |
| Anyone else | — | Nothing (`401`, or the pairing page) |

- **Off by default.** The server listens on `127.0.0.1` unless tablet access is switched on in *System*; only then does
  it listen on all interfaces.
- **Pairing.** A pairing code is valid for 2 minutes, works once, and is void after 5 wrong attempts. A paired device
  keeps a random 256-bit key in an `HttpOnly`, `SameSite=Strict` cookie; `~/.runboard/devices.json` holds only its
  SHA-256 hash. Removing a device in *System* locks it out at once.
- **This computer only.** Saving or removing the Kaggle token, adding or removing projects, the folder browser, the
  new-project wizard, tablet access and the Windows startup setting are refused for paired devices. A paired
  device can restart the dashboard (as it can start and stop runs); a restart does not touch runs in progress.

## Protection against web pages

A page open in your browser must not be able to drive a dashboard on `localhost`.

- **DNS rebinding:** requests must name the machine by IP address, `localhost`, its own host name or a name listed in
  `allowed_hosts` in `~/.runboard/config.yaml`; anything else gets `403`.
- **Cross-site requests:** a state-changing request (`POST`, `DELETE`) whose `Origin` is another site, or that the
  browser marks `Sec-Fetch-Site: cross-site`, gets `403`.
- **Headers:** pages cannot be framed (`X-Frame-Options: DENY`, `frame-ancestors 'none'`), load scripts only from the
  dashboard itself (Content-Security-Policy), and send no referrer.

## Commands in projects

A project's `runboard.yaml` lists commands (training, jobs, the post-run check) that run on this computer with your
user's rights, just like a `Makefile`. Only add projects you trust: when an existing project is added, runboard shows
the commands it would run and asks first. Adding projects is possible only from this computer.

## Secrets

- The Kaggle token is written to `~/.kaggle/access_token` (or read from `KAGGLE_API_TOKEN`) and never returned by any
  endpoint.
- Lines that look like keys or tokens (`KGAT_…`, `token=…`, `password: …`) are masked in logs and job output shown in
  the dashboard. Masking is a safety net, not a guarantee: do not print secrets in training scripts.
- Nothing runboard stores lives inside a project repository.

## Not covered

- **Encryption on the local network.** The dashboard speaks plain HTTP. On a network you do not trust, or from outside
  your home, keep tablet access off or reach the computer through a VPN such as Tailscale (encrypted), and add its
  machine name to `allowed_hosts`.
- **A reverse proxy on the same computer.** Requests through it look local and skip pairing. Do not put runboard
  behind a proxy without adding your own authentication there.
- **Other users of the same computer.** Anyone who can open `localhost` on it can use the dashboard.

## Reporting a vulnerability

Please do not open a public issue. Use GitHub's *Report a vulnerability* (private security advisory) on this
repository, with steps to reproduce. You will get an answer within a week.
