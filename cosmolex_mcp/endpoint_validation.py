"""Exact vendor host allowlists; never accept arbitrary Azure tenants."""

from urllib.parse import urlsplit

LCS_HOSTS = {
    "lcs-developer-api-profi-sandbox-gncndgfccdgxdtff.centralus-01.azurewebsites.net",
    "lcs-developer-api-profitsolv-axc7hfgzafhga5ch.centralus-01.azurewebsites.net",
}


def vendor_endpoint(value: str, hosts: set[str]) -> str:
    try:
        url = urlsplit(value)
        if (
            not value
            or any(ord(c) <= 32 or ord(c) >= 127 for c in value)
            or "\\" in value
            or url.scheme != "https"
            or url.hostname not in hosts
            or url.username is not None
            or url.password is not None
            or url.port not in (None, 443)
            or url.query
            or url.fragment
            or "?" in value
            or "#" in value
            or url.path not in ("", "/")
        ):
            raise ValueError
    except (ValueError, TypeError):
        raise ValueError(
            "Invalid endpoint: use an approved vendor HTTPS host without userinfo, path, query, fragment, or non-default port."
        ) from None
    return value.rstrip("/")
