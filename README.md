# Ecobasa Redesign 2020
Ecobasa is a gift-economy network for sustainable communities

This is a work-in-progress attempt of a redesign.


## Setup for dev

### Postgis
Because we are using postgis for location fields,
you need a postgres db with postgis extensions for this to work, even for development, sorry.

Install postgresql database server and postgis dependencies:
```
apt install libgdal-dev postgis postgresql-12
```

Create normal database in postgres:
```
su postgres
createuser ecobasa
createdb ecobasa -O ecobasa
```

Then add postgis extensions to this database:
```
su postgres
psql -d ecobasa
CREATE EXTENSION postgis;
```

### normal dev setup
```
pipenv install --dev
pipenv shell
python manage.py migrate
npm install
npm run build
```

## Run Tests
```
pytest
```

## Continous Deployment
https://ecobasa.herokuapp.com/

(auto deploys master branch)