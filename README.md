# Ecobasa Redesign 2020
Ecobasa is a gift-economy network for sustainable communities

This is a work-in-progress attempt of a redesign.

What people and communities do on ecobasa:
- **Give and wish for things**: materials, tools, anything else, matched nearby.
- **Share skills**: teach, learn by doing, lend a hand; volunteer at communities and help
  with their projects.
- **Run a tool library**: lend tools instead of giving them away. People ask for the days
  or hours they need something, and a lending calendar shows who has what when.
- **Share cars in a community**: the community's cargo bike, car, trailer or van (their
  own kind, "Vehicle"), booked by the day or the hour, like the tools.


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

The database user must have permission to create a new test database and add postgis extensions:
```
su postgres
psql
ALTER_ROLE ecobasa SUPERUSER;
```

```
pytest
```

## Continous Deployment
https://ecobasa.herokuapp.com/

(auto deploys master branch)
## Reference requests after a match

After a stay ended (or an accepted match's date passed, or a week after acceptance without
a date), both sides get an email asking for a reference, framed for them as their story.
They answer on a no-login form (photo upload works from the phone camera) or by replying
to the email with a photo attached. Staff choose which shared ones appear on the homepage
at `/references/featured/`.

`send_reference_requests` (daily) and `fetch_reference_replies` (every five minutes) run in
the scheduler (see [Scheduled jobs](#scheduled-jobs)).

Settings (env):
- `DJANGO_SITE_URL`: base for links in these emails, e.g. `https://ecobasa.org`
- `REFERENCE_REPLY_ADDRESS`: e.g. `references@ecobasa.org`. Replies go to
  `references+<key>@ecobasa.org`; the key is also in the subject, in case the mail server
  doesn't deliver plus addresses. Leave empty to only offer the link.
- `REFERENCE_IMAP_HOST` (e.g. `mail.ecobytes.net`), `REFERENCE_IMAP_USER`,
  `REFERENCE_IMAP_PASSWORD`, `REFERENCE_IMAP_FOLDER` (default `INBOX`): the mailbox for replies
- `REFERENCE_REQUEST_DELAY_DAYS` (1), `REFERENCE_REQUEST_UNDATED_DELAY_DAYS` (7),
  `REFERENCE_REQUEST_MAX_AGE_DAYS` (30): when to ask, and how far back

In development, replies are read from Mailpit instead of IMAP. Mailpit can't reply itself,
so `python manage.py send_test_reply "text" [--key KEY] [--photo path]` answers the latest
(or a given) request like a mail app would; then run `fetch_reference_replies`.

## Projects

Communities post concrete projects ("Build a rocket stove, March–April, food and bed
provided") with what they need: people with a skill, materials, tools or knowledge.
People offer help on the project page; the offer is a match like a volunteer stay (date-only
counter-proposals, references afterwards). Ambassadors see projects, requested and
confirmed stays and what is still missing in their calendar (`/matches/calendar/<community>/`),
with a warning when more guests are confirmed than the community's maximum.

Projects stay current: dated ones are archived the day after they end; any project nobody
updated or confirmed for `PROJECT_STALE_DAYS` (60) gets an "Is this still current?" email
with a one-click confirm link, and is archived if nobody confirms it within
`PROJECT_ARCHIVE_GRACE_DAYS` (14). Projects without an end date are ongoing.

A project's needs are the community's wishes in it, and what you can learn there its skill
offers in it: both are listed (on the map, in the list, on the community) only while the
project runs.

## Offers and wishes

Everything someone offers or wishes for is one model, `gifts.Listing`: things (material,
tools, anything else), skills, knowledge and helping hands, of a person or a community
(managed by its ambassador), maybe in one of the community's projects. Skills, and
knowledge or helping hands for a known skill, point to the skill vocabulary
(`gifts.Skill`, names in every language, in `gift_economy/gifts/skills/`). With an amount ("200 kg", "2 people") a wish is
covered in parts, and an offer given away in parts: each exchange says how much it brings
or takes (`matches.Contribution`). Covered wishes and given-away offers drop off the lists;
a skill can be shared again and again.

Things have curated vocabularies like skills, one per kind: tools, materials, vehicles and
other things (`gift_economy/gifts/vocabularies/`, in en/de/es/fr with synonyms and broader
things: a stepladder is a ladder, a long john is a cargo bike). The thing in a listing's
title is recognized in the vocabulary of its kind (`gifts.Thing`, `Listing.thing`), also in
plurals and German compounds ("Handkreissäge"), and matching goes by it: the same thing
or a broader or narrower one fits, in any language. Each vocabulary is editable in the
admin; after editing the files, `python manage.py load_vocabularies` loads them and
recognizes existing listings again.

## Lending, tool libraries and car sharing

Tools, vehicles (`Listing.KIND_VEHICLE`: a cargo bike, a car, a trailer, a van) and other
things that come back can be offered **to lend** instead of given away (`Listing.lend`,
preset for vehicles; a wish can be **to borrow**). A request for one says from when until
when (`matches.Loan`): whole days, or from and until an hour ("Sat 14:00–18:00"). Times
on which it is already lent are refused (with an amount, "3 ladders", that many can be
lent at once), the owner can propose other days, and accepting checks again. Lending
doesn't use it up, so it stays listed and matched.

- **Lending calendar** (`/matches/lending/`): once someone lends something or borrows
  something, their dashboard shows a month of who borrows what when (requested and
  agreed), where each thing is today, days asked for by more people than there are
  things, and what they borrow themselves.
- **Tool library of a community**: what a community (and its members) lends is listed
  on the community page under "To borrow here", with whether it is free today. Its
  ambassador gets the community's own lending calendar
  (`/matches/lending/<community>/`, "Tool library" in the dashboard) to track who needs
  what when.
- **Car sharing** works the same way: the community lends its car or van to members by
  the day or the hour and sees all bookings in its lending calendar.

The reference request comes after the day it was brought back.

## Suggestions

As soon as an offer or a wish is saved, the matching (`gift_economy/matches/matching.py`) looks for
what fits it nearby and suggests the pair to both sides: an offer and a wish with the same
skill, or (without one) with similar titles. Each side only hears about things within their own
distance (`User.match_radius`, 150 km by default), or from anywhere if they search worldwide
(`User.match_global`). Without a place they look in their country, and without a country
everywhere (with a one-time notification that they can narrow it down). New suggestions show right away in the
notifications and first on `/matches/`, the one page for gifts and skills (filtered by
either), before the requests received and sent: a suggestion becomes a match once someone
asks. A project's need counts as a gift or a skill by what it needs; volunteer visits and
help with projects have their own page. Once a week, people get an email with what's new
(also those who only have wishes). When a person or community moves, everything that takes its
place from them is matched again. The distance and the email switch are in the profile
("Settings" in the user menu), and every email has a one-click unsubscribe link.

After deploying the matching once, match what already exists:
```
python manage.py match_everything
```

`archive_stale_projects` (daily) and `send_suggestion_emails` (weekly) run in the scheduler
(see [Scheduled jobs](#scheduled-jobs)).

## Scheduled jobs

The jobs that run on their own are in [`crontab`](crontab), run by
[supercronic](https://github.com/aptible/supercronic) in the `scheduler` container (same image
and settings as `django`, times in `TZ`, Europe/Berlin). It logs to the container output, and
skips a job while its previous run is still going.

| When | Command |
| --- | --- |
| every 5 minutes | `fetch_reference_replies` |
| daily, 9:00 | `archive_stale_projects` |
| daily, 10:00 | `send_reference_requests` |
| Thursdays, 17:00 | `send_suggestion_emails` |

To change a time or add a job, edit `crontab` and restart the container
(`docker compose restart scheduler`). Any job can still be run by hand with
`python manage.py <command>`.

In development the scheduler is off, so emails only go out when you run a command. To try it
(emails land in Mailpit):
```
docker compose --profile scheduler up
```
