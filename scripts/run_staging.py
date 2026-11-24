"""Start the isolated staging build with fail-closed deployment configuration."""

import os
from pathlib import Path
from urllib.parse import urlsplit


def validate(environ):
    if environ.get("PLANET_DEPLOYMENT") != "staging":
        raise ValueError("Set PLANET_DEPLOYMENT=staging in the staging service")
    if environ.get("RAILWAY_ENVIRONMENT_NAME", "staging") != "staging":
        raise ValueError("Select the Railway environment named staging")
    mount = environ.get("RAILWAY_VOLUME_MOUNT_PATH")
    data = environ.get("PLANET_DATA_DIR")
    if not mount or not data or Path(mount).resolve() != Path(data).resolve() or not Path(data).is_dir():
        raise ValueError("Mount the dedicated Railway volume at PLANET_DATA_DIR")
    origin = urlsplit(environ.get("PLANET_PUBLIC_ORIGIN", ""))
    if (origin.scheme != "https" or not origin.hostname or origin.username is not None or
            origin.password is not None or origin.path or origin.query or origin.fragment or
            environ.get("PLANET_INSECURE_LOCAL_HTTP") not in {None, "", "0"}):
        raise ValueError("Set the exact staging HTTPS origin and keep secure cookies enabled")
    domain = environ.get("RAILWAY_PUBLIC_DOMAIN")
    if domain and origin.netloc != domain:
        raise ValueError("PLANET_PUBLIC_ORIGIN must match the service's Railway domain")
    if environ.get("PLANET_REQUIRE_VERIFIED_EMAIL") != "1":
        raise ValueError("Set PLANET_REQUIRE_VERIFIED_EMAIL=1 for staging")
    if not all(environ.get(k, "").strip() for k in ("PLANET_RESEND_API_KEY", "PLANET_RESEND_FROM")):
        raise ValueError("Configure Resend credentials and sender before starting email-verified staging")
    if (environ.get("PLANET_STRIPE_KEY") and
            not environ["PLANET_STRIPE_KEY"].startswith(("sk_test_", "rk_test_"))):
        raise ValueError("Use only Stripe test credentials in staging")


if __name__ == "__main__":
    import uvicorn

    try:
        validate(os.environ)
    except ValueError as error:
        raise SystemExit(str(error)) from None
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.environ.get("PORT", "8000")), workers=1)
