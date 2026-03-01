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
		libgettextpo-dev \
	&& rm -rf /var/lib/apt/lists/*

# install Python deps via pipenv using the lockfile
COPY Pipfile Pipfile.lock ./
RUN pip install --no-cache-dir pipenv \
	&& PIPENV_VENV_IN_PROJECT=0 pipenv install --system --deploy

# copy our project code
COPY ./ ${PROJECT_DIR}

# expose the port 8000
EXPOSE 8000

# define the default command to run when starting the container
CMD ["gunicorn", "--bind", ":8000", "wsgi"]