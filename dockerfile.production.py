# start from an official image
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
		PYTHONDONTWRITEBYTECODE=1 \
		PROJECT_DIR=/opt/services/ecobasa

WORKDIR ${PROJECT_DIR}

# install system deps needed for GDAL/geo features and gettext
RUN apt-get update && apt-get install -y --no-install-recommends \
		gdal-bin \
		libgdal-dev \
		proj-bin \
		libproj-dev \
		gettext \
		curl \
		ca-certificates \
		tzdata \
		libgettextpo-dev \
	&& rm -rf /var/lib/apt/lists/*

# install supercronic, the cron for the scheduler container
ARG TARGETARCH=amd64
ENV SUPERCRONIC_VERSION=v0.2.49
RUN case "${TARGETARCH}" in \
		amd64) SUPERCRONIC_SHA1SUM=e63c11a9726b775a6a11801e81af4f3fb926aa68 ;; \
		arm64) SUPERCRONIC_SHA1SUM=0b6c5bb743e0b0dafed1132198c81807927ac413 ;; \
		*) echo "no supercronic for ${TARGETARCH}" && exit 1 ;; \
	esac \
	&& SUPERCRONIC=supercronic-linux-${TARGETARCH} \
	&& curl -fsSLO "https://github.com/aptible/supercronic/releases/download/${SUPERCRONIC_VERSION}/${SUPERCRONIC}" \
	&& echo "${SUPERCRONIC_SHA1SUM}  ${SUPERCRONIC}" | sha1sum -c - \
	&& chmod +x "${SUPERCRONIC}" \
	&& mv "${SUPERCRONIC}" /usr/local/bin/supercronic

# install Python deps via pipenv using the lockfile
COPY Pipfile Pipfile.lock ./
RUN pip install --no-cache-dir pipenv \
	&& PIPENV_VENV_IN_PROJECT=0 pipenv install --system --deploy

# copy our project code
COPY ./ ${PROJECT_DIR}

# compile translations (.mo files are not committed)
RUN django-admin compilemessages --ignore=node_modules --ignore=.venv

# expose the port 8000
EXPOSE 8000

# define the default command to run when starting the container
CMD ["gunicorn", "--bind", ":8000", "wsgi"]