# start from an official image
FROM python:3.8

ENV PYTHONUNBUFFERED=1

# arbitrary location choice: you can change the directory
RUN mkdir -p /opt/services/ecobasa
WORKDIR /opt/services/ecobasa

# copy our project code
COPY ./ /opt/services/ecobasa/

# install our dependencies
RUN pip install pipenv
RUN pipenv install --system
RUN apt-get update && apt-get install -y \
	libgdal-dev \
	gettext \
	libgettextpo-dev

# expose the port 8000
EXPOSE 8000

# define the default command to run when starting the container
CMD ["gunicorn", "--bind", ":8000", "wsgi"]