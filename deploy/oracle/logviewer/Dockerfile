# Custom logviewer image: upstream logviewer + an Apple dark-mode skin and
# Pebble link-preview (Open Graph) branding.
#
# We keep the upstream app and all of its message-rendering templates untouched,
# and only overlay one extra stylesheet (applemode.css) plus replace the page
# metadata. No template logic is modified.
FROM ghcr.io/modmail-dev/logviewer:master

# Apple dark-mode skin + the link-preview image (served at /static/img/og.png).
COPY static/css/applemode.css /logviewer/static/css/applemode.css
COPY static/img/og.png        /logviewer/static/img/og.png

# Inject the Apple stylesheet, set the Pebble link-preview (Open Graph) tags,
# and rebrand the page title. The og:* tags shown when a log link is shared
# (e.g. in Discord) become a fixed Pebble card instead of leaking recipient
# details — and point at our own self-hosted image so they never expire.
RUN set -eux; \
    for f in base.html logbase.html; do \
        t="/logviewer/templates/$f"; \
        # drop the upstream per-thread og:* tags and any existing theme-color
        sed -i '/property=.og:/d; /name=.theme-color./d' "$t"; \
        # rebrand the browser/tab title
        sed -i 's#<title>[^<]*</title>#<title>Pebble</title>#' "$t"; \
        # inject our stylesheet + Open Graph card just before </head>
        sed -i 's@</head>@\
    <link href="/static/css/applemode.css" type="text/css" rel="stylesheet" media="screen,projection" />\
    <meta property="og:type" content="website" />\
    <meta property="og:site_name" content="Pebble" />\
    <meta property="og:title" content="Pebble" />\
    <meta property="og:description" content="Pebble logs are used by Plover contributors to assist in customer support inquiries." />\
    <meta property="og:image" content="https://pebble.getplover.com/static/img/og.png" />\
    <meta name="twitter:card" content="summary_large_image" />\
    <meta name="theme-color" content="#0A84FF" />\
</head>@' "$t"; \
    done
