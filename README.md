# Developer utility APIs + remote MCP servers

Thirteen small, focused REST APIs for everyday developer jobs: validating emails, phones and IBANs, IP geolocation, PDFs, images, QR codes, fraud scoring, token counting and more. Each one is its own product on [RapidAPI](https://rapidapi.com/user/Olly-1VN9JTXKG) with a **free plan**, full OpenAPI docs, and a built-in **remote MCP server** so AI agents (Claude, Cursor, VS Code, n8n, LangChain) can call it as tools.

- **Free tier on every API**: subscribe on RapidAPI, copy your key, call it.
- **MCP built in**: every API exposes Streamable HTTP MCP at `https://<host>.p.rapidapi.com/mcp`, and each is listed in the [official MCP Registry](https://registry.modelcontextprotocol.io) as `io.github.OlsOls4/<kit>`.
- **No heavy dependencies on your side**: plain HTTPS + JSON from any language or no-code tool.

## The APIs

| API | What it does | RapidAPI | MCP endpoint | Tutorial |
|---|---|---|---|---|
| **WebKit** | Email validation, link previews and article-to-Markdown extraction for AI agents | [Listing](https://rapidapi.com/Olly-1VN9JTXKG/api/webkit-email-validator-link-preview-article-extractor) | `https://webkit-email-validator-link-preview-article-extractor.p.rapidapi.com/mcp` | [dev.to](https://dev.to/olly_08beff75f1fe547dcb92/catch-janegmialcom-at-signup-email-validation-with-typo-suggestions-44b3) |
| **DomainKit** | DNS records, SSL certificate, WHOIS/RDAP and website tech scan for any domain | [Listing](https://rapidapi.com/Olly-1VN9JTXKG/api/domainkit-dns-ssl-whois-website-tech-lookup) | `https://domainkit-dns-ssl-whois-website-tech-lookup.p.rapidapi.com/mcp` | [dev.to](https://dev.to/olly_08beff75f1fe547dcb92/monitor-ssl-expiry-and-security-headers-for-any-domain-with-one-api-46ek) |
| **QRKit** | Generate QR codes (URL, WiFi, vCard) and barcodes as PNG/SVG | [Listing](https://rapidapi.com/Olly-1VN9JTXKG/api/qrkit-qr-code-barcode-generator) | `https://qrkit-qr-code-barcode-generator.p.rapidapi.com/mcp` | [dev.to](https://dev.to/olly_08beff75f1fe547dcb92/generate-qr-codes-wi-fi-qr-codes-and-barcodes-from-a-url-no-library-needed-31g7) |
| **TextKit** | Sentiment, language detection, readability, keywords, summaries and profanity filtering | [Listing](https://rapidapi.com/Olly-1VN9JTXKG/api/textkit-sentiment-language-readability-keywords) | `https://textkit-sentiment-language-readability-keywords.p.rapidapi.com/mcp` | [dev.to](https://dev.to/olly_08beff75f1fe547dcb92/sentiment-language-keywords-and-readability-in-a-single-api-call-4hk0) |
| **PhoneKit** | Phone number validation, formatting, carrier, line type and timezone | [Listing](https://rapidapi.com/Olly-1VN9JTXKG/api/phonekit-phone-number-validation-carrier-line-type) | `https://phonekit-phone-number-validation-carrier-line-type.p.rapidapi.com/mcp` | [dev.to](https://dev.to/olly_08beff75f1fe547dcb92/validate-phone-numbers-in-3-lines-of-python-carrier-line-type-e164-47he) |
| **ValidKit** | Validate IBAN, EU VAT, card numbers, ISBN, BIC, EAN and postcodes | [Listing](https://rapidapi.com/Olly-1VN9JTXKG/api/validkit-iban-vat-card-isbn-bic-postcode-validator) | `https://validkit-iban-vat-card-isbn-bic-postcode-validator.p.rapidapi.com/mcp` | [dev.to](https://dev.to/olly_08beff75f1fe547dcb92/one-api-for-checkout-form-validation-iban-eu-vat-card-numbers-postcodes-78f) |
| **GeoIP** | IP geolocation: country, continent, ASN and ISP lookup | [Listing](https://rapidapi.com/Olly-1VN9JTXKG/api/geoip-ip-geolocation-asn-isp-lookup) | `https://geoip-ip-geolocation-asn-isp-lookup.p.rapidapi.com/mcp` | [dev.to](https://dev.to/olly_08beff75f1fe547dcb92/ip-geolocation-asn-in-one-call-and-why-asn-matters-for-fraud-58b4) |
| **DocKit** | Extract text and metadata from PDFs; convert Markdown or text to PDF | [Listing](https://rapidapi.com/Olly-1VN9JTXKG/api/dockit-pdf-text-extraction-markdown-to-pdf) | `https://dockit-pdf-text-extraction-markdown-to-pdf.p.rapidapi.com/mcp` | [dev.to](https://dev.to/olly_08beff75f1fe547dcb92/extract-text-from-pdfs-for-your-llmrag-pipeline-with-one-http-call-1167) |
| **FraudKit** | Fraud risk score for signups and orders from email, IP, phone and user-agent | [Listing](https://rapidapi.com/Olly-1VN9JTXKG/api/fraudkit-fraud-risk-score-for-signups-orders) | `https://fraudkit-fraud-risk-score-for-signups-orders.p.rapidapi.com/mcp` | [dev.to](https://dev.to/olly_08beff75f1fe547dcb92/a-fraud-risk-score-for-signups-and-orders-in-one-api-call-1pcd) |
| **ImageKit** | Resize, convert to WebP, compress, crop, rotate and strip EXIF from images | [Listing](https://rapidapi.com/Olly-1VN9JTXKG/api/imagekit-resize-convert-to-webp-compress-crop) | `https://imagekit-resize-convert-to-webp-compress-crop.p.rapidapi.com/mcp` | [dev.to](https://dev.to/olly_08beff75f1fe547dcb92/resize-convert-to-webp-and-compress-images-over-http-no-sharp-no-imagemagick-2jbe) |
| **UK PostcodeKit** | UK postcode lookup, nearest postcodes, autocomplete and distance (OS open data) | [Listing](https://rapidapi.com/Olly-1VN9JTXKG/api/uk-postcodekit-postcode-lookup-nearest-distance) | `https://uk-postcodekit-postcode-lookup-nearest-distance.p.rapidapi.com/mcp` | [dev.to](https://dev.to/olly_08beff75f1fe547dcb92/uk-postcode-lookup-nearest-postcodes-and-distance-in-one-api-362o) |
| **LLMKit** | Token counting, RAG chunking, truncation, HTML to Markdown and JSON repair | [Listing](https://rapidapi.com/Olly-1VN9JTXKG/api/llmkit-token-counter-rag-chunker-json-repair) | `https://llmkit-token-counter-rag-chunker-json-repair.p.rapidapi.com/mcp` | [dev.to](https://dev.to/olly_08beff75f1fe547dcb92/count-tokens-chunk-for-rag-and-repair-llm-json-with-one-http-call-no-tiktoken-install-2lc4) |
| **CalKit** | Public holidays for 150+ countries, business-day maths and timezone lookup | [Listing](https://rapidapi.com/Olly-1VN9JTXKG/api/calkit-public-holidays-business-days-timezones) | `https://calkit-public-holidays-business-days-timezones.p.rapidapi.com/mcp` | [dev.to](https://dev.to/olly_08beff75f1fe547dcb92/add-5-business-days-is-harder-than-it-looks-heres-an-api-for-it-4oio) |

Also available (newer):

- **CurrencyKit**: ECB euro reference exchange rates: latest, historical, time series and currency conversion. [RapidAPI](https://rapidapi.com/Olly-1VN9JTXKG/api/currencykit-ecb-exchange-rates-currency-converter) · MCP `https://currencykit-ecb-exchange-rates-currency-converter.p.rapidapi.com/mcp`
- **VATKit**: Live EU VAT number checks via VIES with company name/address, VAT formats and EU VAT rates. [RapidAPI](https://rapidapi.com/Olly-1VN9JTXKG/api/vatkit-eu-vat-number-check-vies-vat-rates) · MCP `https://vatkit-eu-vat-number-check-vies-vat-rates.p.rapidapi.com/mcp`

## Quickstart (REST)

```bash
curl -G "https://calkit-public-holidays-business-days-timezones.p.rapidapi.com/business-days/add" \
  -d date=2026-12-23 -d days=5 -d country=GB -d subdiv=ENG \
  -H "X-RapidAPI-Key: YOUR_RAPIDAPI_KEY" \
  -H "X-RapidAPI-Host: calkit-public-holidays-business-days-timezones.p.rapidapi.com"
```

Swap the host for any API in the table. Every request goes through RapidAPI with `X-RapidAPI-Key` and `X-RapidAPI-Host`.

## Quickstart (MCP)

Add any API as a remote MCP server in a client that supports Streamable HTTP with custom headers, for example:

```json
{
  "mcpServers": {
    "calkit": {
      "type": "http",
      "url": "https://calkit-public-holidays-business-days-timezones.p.rapidapi.com/mcp",
      "headers": {
        "X-RapidAPI-Key": "YOUR_RAPIDAPI_KEY",
        "X-RapidAPI-Host": "calkit-public-holidays-business-days-timezones.p.rapidapi.com"
      }
    }
  }
}
```

The server answers `tools/list` with that API's endpoints as tools.

## What's in this repo

- `main.py` and one folder per API (`webkit`, `domainkit`, `qrkit`, ...): the FastAPI service behind all listings.
- `mcpserver.py`: the MCP layer that turns each API's routes into tools.
- `openapi/`: OpenAPI specs for each API.
- `mcp-registry/`: `server.json` files published to the official MCP Registry.

## Data and licences

GeoIP and FraudKit use DB-IP Lite (CC BY 4.0). UK PostcodeKit uses OS Code-Point Open (Open Government Licence v3.0; contains OS data © Crown copyright and database right). PhoneKit uses Google libphonenumber (Apache 2.0). Full attributions are in each API's docs on RapidAPI.

## Support

Questions, bugs or feature requests: [open an issue](https://github.com/OlsOls4/webkit-api/issues) or use the Discussions tab on the RapidAPI listing.
