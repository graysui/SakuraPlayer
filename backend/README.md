# SakuraPlayer Backend

The backend is a private Docker deployment for one administrator. Compose publishes the API on `127.0.0.1:8000` by default and never publishes PostgreSQL to the host.

Remote clients must connect through HTTPS or a trusted encrypted VPN. This repository does not provide a public internet deployment guide, automatic certificate issuance, or a plaintext public endpoint.

Create the five secret files referenced by `.env.example` outside version control, then run Docker Compose from this directory. The one-shot `migrate` service performs the explicit Alembic upgrade; API, worker, and scheduler only check the Schema head and never migrate it. The long-running processes start only after migration succeeds.

The four named volumes keep PostgreSQL data, permanent catalog images, provider manifests, and necessary redacted logs separate. v1 does not create an automatic backup for the database or images. Operators must arrange any desired backup outside SakuraPlayer.

Windows delivery uses a private installer. HarmonyOS delivery remains blocked until the Windows and real 115 gates pass, then uses developer-signed sideloading. No public app-store workflow is included.

See `../LICENSE` and `../THIRD_PARTY_NOTICES.md` before redistributing builds or imported source.
