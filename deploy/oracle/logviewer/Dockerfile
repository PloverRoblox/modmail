# Custom logviewer image: upstream logviewer + an Apple dark-mode skin.
#
# We keep the upstream app and all of its message-rendering templates untouched,
# and only overlay one extra stylesheet (applemode.css) that overrides the look.
# The stylesheet is injected as the LAST <link> in each template so it wins the
# CSS cascade — no template logic is modified.
FROM ghcr.io/modmail-dev/logviewer:master

COPY static/css/applemode.css /logviewer/static/css/applemode.css

# Append the Apple stylesheet right before </head> in both page templates.
RUN sed -i 's#</head>#    <link href="/static/css/applemode.css" type="text/css" rel="stylesheet" media="screen,projection" />\n</head>#' \
        /logviewer/templates/base.html \
        /logviewer/templates/logbase.html
