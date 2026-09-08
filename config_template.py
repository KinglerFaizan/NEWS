"""
config.py  —  RENAME THIS FILE TO `config.py` and place it beside audit_intel_app.py

Any subset of the three keys may be defined. The app falls back to environment
variables, then Streamlit secrets, then the in-page password fields.

Tiering
    PRIMARY  NewsAPI.org + APITube.io   run together on every refresh
    RESERVE  NewsData.io                idle until BOTH primaries hit their limits

Free-tier limits (verify current values with each provider)
    NewsAPI.org   100 requests/day    100 results/request   1 month history
    APITube.io    100 requests/day     10 results/request   10 req/min, 12h delay
    NewsData.io   200 credits/day      10 results/request
"""

# https://newsapi.org/register
NEWSAPI_KEY = ""

# https://apitube.io/  — dashboard shows the key after signup
APITUBE_KEY = ""

# https://newsdata.io/register
NEWSDATA_KEY = ""
