# One static container: the film page and the two measured videos, served by nginx. No keys, no server code.
# The build context is prepared by deploy/deploy.sh: a clean `git archive` of HEAD plus public/ written by tools/site.py.
FROM nginx:1.27-alpine
RUN rm /etc/nginx/conf.d/default.conf
COPY deploy/nginx.conf /etc/nginx/conf.d/sampan-river.conf
COPY public/ /usr/share/nginx/html/
# Run as the unprivileged nginx user on port 8080, with every writable path under /tmp (the root file system is read-only).
RUN sed -i -e 's|^pid .*|pid /tmp/nginx.pid;|' -e '/^user /d' /etc/nginx/nginx.conf
USER nginx
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD wget -qO- http://127.0.0.1:8080/healthz || exit 1
